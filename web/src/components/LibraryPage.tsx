import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { ingest } from '../api/ingest'
import { SOURCE_POLL_INTERVAL_MS } from '../config'
import { rag } from '../api/rag'
import type { LibraryEntry, Notebook, Output, TrashEntry } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { formatBytes, formatTime } from '../lib/format'
import { kindWithCapture } from '../lib/capture'
import { addPlan, addedSummary, bulkDeleteConfirmText, deleteConfirmText, filterLibrary, notebookTitleFrom, purgeIn, type LibraryFilter } from '../lib/library'
import { audioFiles, openTarget } from '../lib/openEntry'
import { OUTPUT_FORMS, SOURCE_FORMS, formFor, sourceKindLabel } from '../lib/outputs'
import { DemoBadge } from './DemoBadge'
import { AudioCheck, PlayButton } from './AudioCheck'
import { ImageName } from './ImageName'
import { ReadOnlyOutput, TrashedOutputs } from './LibraryOutputs'
import { PendingReason } from './PendingReason'
import { RedeemLink } from './RedeemLink'
import { ShareCard } from './ShareCard'
import { t, tn } from '../i18n'

interface Props {
  /** with `outputId`, that document is selected when the notebook opens */
  onOpenNotebook: (id: string, outputId?: string) => void
  /** the settings page, at the trash-days field */
  onOpenSettings: () => void
}

/** /library: every upload and URL of the user and every generated
 *  document, in one table with the notebooks each is in, and the trash of
 *  both. Removing a source in a notebook only detaches it;
 *  deleting here moves it to the trash (out of every notebook, after a
 *  confirmation that names them), from where it is restored or purged. */
export function LibraryPage({ onOpenNotebook, onOpenSettings }: Props) {
  const [view, setView] = useState<'library' | 'trash'>('library')
  return (
    <main className="library">
      <h1>{t('lib.title')}</h1>
      <nav className="subnav" aria-label={t('lib.views')}>
        {(['library', 'trash'] as const).map((v) => (
          <a
            key={v}
            href="/library"
            className={view === v ? 'active' : undefined}
            aria-current={view === v ? 'page' : undefined}
            onClick={(e) => {
              e.preventDefault()
              setView(v)
            }}
          >
            {v === 'library' ? t('lib.title') : t('lib.trash')}
          </a>
        ))}
      </nav>
      {view === 'library' ? (
        <LibraryList onOpenNotebook={onOpenNotebook} />
      ) : (
        <>
          <TrashList onOpenSettings={onOpenSettings} />
          <TrashedOutputs />
        </>
      )}
    </main>
  )
}

/** The title field and the create button of the selection bar. The title
 *  follows the selection until it is edited; Enter or the button creates,
 *  Escape clears the field. Unmounted with the bar, so a new selection
 *  starts from its own title again. */
function NotebookFromSelection({ selected, busy, onCreate }: { selected: LibraryEntry[]; busy: boolean; onCreate: (title: string) => void }) {
  const [edited, setEdited] = useState<string | null>(null)
  const title = edited ?? notebookTitleFrom(selected)

  function submit(e: FormEvent) {
    e.preventDefault()
    if (title.trim()) onCreate(title.trim())
  }

  return (
    <form className="notebook-from" onSubmit={submit}>
      <input
        aria-label={t('lib.notebookTitlePrompt')}
        placeholder={t('lib.notebookTitlePrompt')}
        value={title}
        onChange={(e) => setEdited(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setEdited('')
        }}
      />
      <button type="submit" className="secondary" disabled={busy || !title.trim()}>
        {tn('lib.notebookFromN', selected.length)}
      </button>
    </form>
  )
}

const withoutGenerated = <T extends { kind: string }>(list: T[]): T[] => list.filter((e) => e.kind !== 'generated')
const isDoc = (e: LibraryEntry) => e.kind === 'generated'

/** The library as one table: uploads and outputs together,
 *  narrowed by a view (all, sources, outputs), a kind, a notebook and a
 *  part of the name. A document's kind and status come from rag's list of
 *  the user's outputs (joined by `output_id`); it opens in the notebook it
 *  was made in, or read-only here once that notebook is gone, and is
 *  deleted through rag. Ticked rows can start a notebook, be added to one
 *  (only those not in it yet) or be deleted. */
function LibraryList({ onOpenNotebook }: Pick<Props, 'onOpenNotebook'>) {
  const [entries, setEntries] = useState<LibraryEntry[]>([])
  const [outputs, setOutputs] = useState<Map<string, Output>>(new Map())
  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [filter, setFilter] = useState<LibraryFilter>({ view: 'all', kind: 'all', query: '', notebook: 'all' })
  // ticked rows, kept across filtering; actions apply to those still listed
  const [picked, setPicked] = useState<Set<string>>(new Set())
  // the one audio entry whose player is open, with the files taken then
  const [playing, setPlaying] = useState<{ id: string; files: NonNullable<ReturnType<typeof audioFiles>> } | null>(null)
  const [progress, setProgress] = useState<{ kind: 'delete' | 'add'; done: number; total: number } | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [reading, setReading] = useState<Output | null>(null)
  // the output row whose share card is open
  const [sharing, setSharing] = useState<string | null>(null)
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => {
      const [list, outs, nbs] = await Promise.all([ingest.listLibrary('all'), rag.libraryOutputs(), ingest.listNotebooks()])
      setEntries(list)
      setOutputs(new Map(outs.map((o) => [o.id, o])))
      setNotebooks(nbs)
    })
  }, [run])

  // new entries (a new account's demo sources, say) turn ready as the worker gets to them
  const processing = entries.some((e) => e.status === 'processing' || e.status === 'waiting_for_credit')
  useEffect(() => {
    if (!processing) return
    const timer = setInterval(() => {
      ingest.listLibrary('all').then(setEntries, () => {
        // a failed poll is retried on the next tick
      })
    }, SOURCE_POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [processing])

  const output = (e: LibraryEntry) => (e.output_id ? outputs.get(e.output_id) : undefined)
  const docKind = (e: LibraryEntry) => output(e)?.kind ?? null
  // a document links only once it is ready (ingest refuses the whole call otherwise)
  const linkable = (e: LibraryEntry) => !isDoc(e) || (output(e)?.status ?? 'ready') === 'ready'

  function drop(id: string) {
    setEntries((prev) => prev.filter((x) => x.id !== id))
    setPicked((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }

  // an upload goes to ingest's trash, a document to rag's
  const trash = (e: LibraryEntry) => (isDoc(e) && e.output_id ? rag.deleteOutput(e.output_id) : ingest.deleteLibraryEntry(e.id))

  async function remove(e: LibraryEntry) {
    if (!confirm(deleteConfirmText(e))) return
    if (await run(() => trash(e).then(() => true))) drop(e.id)
  }

  async function open(e: LibraryEntry) {
    if (e.origin?.id && e.output_id) {
      onOpenNotebook(e.origin.id, e.output_id)
      return
    }
    const id = e.output_id
    if (!id) return
    const full = await run(() => rag.getOutput(id))
    if (full) setReading(full)
  }

  const shown = filterLibrary(entries, filter, docKind)
  const waiting = entries.filter((e) => e.status === 'waiting_for_credit').length
  const selected = entries.filter((e) => picked.has(e.id))
  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  /** One delete per entry, in order; after a failure the rest stays ticked. */
  async function removeSelected() {
    if (selected.length === 0 || !confirm(bulkDeleteConfirmText(selected))) return
    setNotice(null)
    await run(async () => {
      let done = 0
      setProgress({ kind: 'delete', done, total: selected.length })
      try {
        for (const e of selected) {
          await trash(e)
          done += 1
          setProgress({ kind: 'delete', done, total: selected.length })
          drop(e.id)
        }
      } finally {
        setProgress(null)
      }
    })
  }

  /** The entries not in the notebook yet, in one call; the rows learn
   *  their new notebook from a fresh list. */
  async function addTo(nb: Notebook) {
    const plan = addPlan(selected, nb.id, linkable)
    if (plan.toAdd.length === 0) return
    setNotice(null)
    const r = await run(() => ingest.addManyFromLibrary(nb.id, plan.toAdd))
    if (!r) return
    setNotice(addedSummary(r.added.length, plan.already + r.already.length, nb.title))
    const list = await run(() => ingest.listLibrary('all'))
    if (list) setEntries(list)
  }

  /** A notebook with the title from the selection bar, the entries linked
   *  in one call, then opened. */
  async function notebookFromSelected(title: string) {
    const ids = selected.filter(linkable).map((e) => e.id)
    if (ids.length === 0 || !title) return
    const id = await run(async () => {
      const nb = await ingest.createNotebook(title)
      await ingest.addManyFromLibrary(nb.id, ids)
      return nb.id
    })
    if (id) onOpenNotebook(id)
  }

  if (reading) return <ReadOnlyOutput output={reading} onBack={() => setReading(null)} />

  const kinds: { value: string; label: string }[] = [
    ...(filter.view !== 'outputs' ? SOURCE_FORMS.map((f) => ({ value: f.kind, label: f.label })) : []),
    ...(filter.view !== 'sources' ? OUTPUT_FORMS.map((f) => ({ value: f.kind, label: f.label })) : []),
  ]

  return (
    <>
      <p className="muted small">{t('lib.intro')}</p>
      <div className="library-views kind-chips" role="group" aria-label={t('lib.view')}>
        {(['all', 'sources', 'outputs'] as const).map((v) => (
          <button
            key={v}
            type="button"
            className={filter.view === v ? 'preset active' : 'preset'}
            aria-pressed={filter.view === v}
            onClick={() => setFilter({ ...filter, view: v, kind: 'all' })}
          >
            {t(`lib.view.${v}`)}
          </button>
        ))}
      </div>
      <div className="filters">
        <label>
          {t('lib.kind')}
          <select value={filter.kind} onChange={(e) => setFilter({ ...filter, kind: e.target.value as LibraryFilter['kind'] })}>
            <option value="all">{t('lib.all')}</option>
            {kinds.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('lib.notebook')}
          <select value={filter.notebook} onChange={(e) => setFilter({ ...filter, notebook: e.target.value })}>
            <option value="all">{t('lib.all')}</option>
            <option value="none">{t('lib.notInAny')}</option>
            {notebooks.map((n) => (
              <option key={n.id} value={n.id}>
                {n.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('lib.name')}
          <input type="search" value={filter.query} placeholder={t('lib.searchPlaceholder')} onChange={(e) => setFilter({ ...filter, query: e.target.value })} />
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice small">{notice}</p>}
      {waiting > 0 && (
        <p className="notice small waiting">
          {tn('lib.waitingN', waiting)} · <RedeemLink />
        </p>
      )}
      {selected.length > 0 && (
        <div className="selection-bar" role="region" aria-label={tn('lib.selected', selected.length)}>
          <span className="muted small">{progress ? t(progress.kind === 'delete' ? 'lib.progressDelete' : 'lib.progressAdd', { done: progress.done, total: progress.total }) : tn('lib.selected', selected.length)}</span>
          <NotebookFromSelection selected={selected} busy={busy} onCreate={(title) => void notebookFromSelected(title)} />
          <AddToNotebook selected={selected} notebooks={notebooks} linkable={linkable} busy={busy} onAdd={(nb) => void addTo(nb)} />
          <button type="button" className="danger" disabled={busy} onClick={() => void removeSelected()}>
            {tn('lib.deleteN', selected.length)}
          </button>
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th className="pick-col">
              <span className="pick-all">
                <button type="button" className="link small" disabled={shown.length === 0 || shown.every((e) => picked.has(e.id))} onClick={() => setPicked((prev) => new Set([...prev, ...shown.map((e) => e.id)]))}>
                  {t('lib.selectAll')}
                </button>
                /
                <button type="button" className="link small" disabled={!shown.some((e) => picked.has(e.id))} onClick={() => setPicked((prev) => new Set([...prev].filter((id) => !shown.some((e) => e.id === id))))}>
                  {t('lib.selectNone')}
                </button>
              </span>
            </th>
            <th>{t('lib.name')}</th>
            <th>{t('lib.kind')}</th>
            <th>{t('lib.status')}</th>
            <th>{t('lib.size')}</th>
            <th>{t('lib.added')}</th>
            <th>{t('lib.inNotebooks')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {shown.map((e) => {
            const doc = isDoc(e)
            const out = output(e)
            const href = doc ? null : openTarget(e)
            const files = doc ? null : audioFiles(e)
            const status = doc && out ? out.status : e.status
            return (
              <Fragment key={e.id}>
                <tr className={picked.has(e.id) ? 'picked' : undefined}>
                  <td className="pick-col">
                    <input type="checkbox" checked={picked.has(e.id)} onChange={() => toggle(e.id)} aria-label={t('lib.selectRow', { name: e.name })} />
                  </td>
                  <td className="name">
                    <span className="name-cell">
                      {href ? (
                        <a className="open-name" href={href} target="_blank" rel="noopener noreferrer" title={t('lib.openTitle', { name: e.name })}>
                          <ImageName kind={e.kind} previewUrl={e.preview_url} label={e.name} title={e.url ?? e.name} thumbnail={false} />
                        </a>
                      ) : (
                        <ImageName kind={e.kind} previewUrl={e.preview_url} label={e.name} title={e.url ?? e.name} thumbnail={false} />
                      )}
                      <DemoBadge demo={e.demo} />
                    </span>
                  </td>
                  <td>{doc ? (out ? formFor(out.kind).label : sourceKindLabel(e.kind)) : kindWithCapture(sourceKindLabel(e.kind), e.capture)}</td>
                  <td className="status-cell">
                    <span className={`badge ${status}`} title={e.status === 'failed' && e.error ? e.error : undefined}>
                      {t(`status.${status}`)}
                    </span>
                    {e.status === 'failed' && e.error && (
                      <span className="error small reason" title={e.error}>
                        {e.error}
                      </span>
                    )}
                    <PendingReason status={e.status} error={e.error} className="reason" />
                  </td>
                  <td>
                    {doc ? (
                      <span className="muted small">—</span>
                    ) : e.size_bytes === null ? (
                      <span className="muted small" title={t('lib.sizeUnknownTitle')}>
                        {t('lib.sizeUnknown')}
                      </span>
                    ) : (
                      formatBytes(e.size_bytes)
                    )}
                  </td>
                  <td>{formatTime(e.created_at)}</td>
                  <td>
                    {doc && e.origin && (
                      <span className={e.origin.id ? 'muted small made-in' : 'muted small made-in gone'}>
                        {e.origin.id ? t('lib.madeIn', { title: e.origin.title }) : t('lib.madeInDeleted', { title: e.origin.title })}
                      </span>
                    )}
                    {e.notebooks.length === 0 ? (
                      !doc && <span className="muted small">{t('lib.notInAny')}</span>
                    ) : (
                      <span className="where-used">
                        {e.notebooks.map((n) => (
                          <a
                            key={n.id}
                            href="/"
                            onClick={(ev) => {
                              ev.preventDefault()
                              onOpenNotebook(n.id)
                            }}
                          >
                            {n.title}
                          </a>
                        ))}
                      </span>
                    )}
                  </td>
                  <td className="row-actions">
                    {files && <PlayButton open={playing?.id === e.id} name={e.name} onToggle={() => setPlaying((p) => (p?.id === e.id ? null : { id: e.id, files }))} />}
                    {doc && out && out.status === 'ready' && (
                      <button type="button" className="link" aria-expanded={sharing === e.id} onClick={() => setSharing((s) => (s === e.id ? null : e.id))}>
                        {out.share_token ? t('viewer.shared') : t('viewer.share')}
                      </button>
                    )}
                    {doc ? (
                      <button type="button" className="link" disabled={busy || !e.output_id} title={e.origin?.id ? t('lib.out.openTitle', { title: e.name }) : t('lib.out.openReadOnly', { title: e.name })} onClick={() => void open(e)}>
                        {t('lib.open')}
                      </button>
                    ) : href ? (
                      <a className="link" href={href} target="_blank" rel="noopener noreferrer">
                        {t('lib.open')}
                      </a>
                    ) : (
                      <button type="button" className="link" disabled title={t('lib.openUnavailable')}>
                        {t('lib.open')}
                      </button>
                    )}
                    <button type="button" className="link danger" disabled={busy} onClick={() => void remove(e)}>
                      {t('common.delete')}
                    </button>
                  </td>
                </tr>
                {sharing === e.id && out && (
                  <tr className="share-row">
                    <td colSpan={8}>
                      <ShareCard output={out} onChanged={(token) => setOutputs((m) => new Map(m).set(out.id, { ...out, share_token: token }))} />
                    </td>
                  </tr>
                )}
                {playing?.id === e.id && (
                  <tr className="audio-row">
                    <td colSpan={8}>
                      <AudioCheck files={playing.files} />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
          {shown.length === 0 && !busy && (
            <tr>
              <td className="muted" colSpan={8}>
                {entries.length === 0 ? t('lib.empty') : t('lib.noMatch')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  )
}

/** "Add to notebook…": the user's notebooks, each saying how many of the
 *  ticked entries are in it already; a click adds only the others. A
 *  notebook that has all of them is disabled and says so. */
function AddToNotebook({ selected, notebooks, linkable, busy, onAdd }: { selected: LibraryEntry[]; notebooks: Notebook[]; linkable: (e: LibraryEntry) => boolean; busy: boolean; onAdd: (nb: Notebook) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="add-to">
      <button type="button" className="secondary" disabled={busy || notebooks.length === 0} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {t('lib.addTo')}
      </button>
      {open && (
        <ul className="add-to-list" role="menu">
          {notebooks.map((nb) => {
            const plan = addPlan(selected, nb.id, linkable)
            const full = plan.toAdd.length === 0
            return (
              <li key={nb.id} role="none">
                <button
                  type="button"
                  role="menuitem"
                  className="item"
                  disabled={busy || full}
                  title={full ? (plan.skipped ? t('lib.notReadyTitle') : t('lib.allInTitle')) : undefined}
                  onClick={() => {
                    setOpen(false)
                    onAdd(nb)
                  }}
                >
                  <span className="add-to-name">{nb.title}</span>
                  <span className="muted small">
                    {full && plan.already === selected.length ? t('lib.allIn') : t('lib.someIn', { n: plan.already, total: selected.length })}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </span>
  )
}

/** Deleted entries until they are purged: restore puts one back in the
 *  library (in no notebook), delete removes it for good. */
function TrashList({ onOpenSettings }: Pick<Props, 'onOpenSettings'>) {
  const [entries, setEntries] = useState<TrashEntry[]>([])
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => setEntries(withoutGenerated(await ingest.listTrash())))
  }, [run])

  async function restore(e: TrashEntry) {
    const ok = await run(async () => {
      await ingest.restoreFromTrash(e.id)
      return true
    })
    if (ok) setEntries((prev) => prev.filter((x) => x.id !== e.id))
  }

  async function purge(e: TrashEntry) {
    if (!confirm(t('lib.purgeConfirm', { name: e.name }))) return
    const ok = await run(async () => {
      await ingest.purgeFromTrash(e.id)
      return true
    })
    if (ok) setEntries((prev) => prev.filter((x) => x.id !== e.id))
  }

  return (
    <>
      <p className="muted small">
        {t('lib.trashIntro.before')}
        <a
          href="/settings#trash-days"
          onClick={(e) => {
            e.preventDefault()
            onOpenSettings()
          }}
        >
          {t('lib.trashIntro.link')}
        </a>
        {t('lib.trashIntro.after')}
      </p>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>{t('lib.name')}</th>
            <th>{t('lib.kind')}</th>
            <th>{t('lib.size')}</th>
            <th>{t('lib.deleted')}</th>
            <th>{t('lib.purge')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id}>
              <td className="name">
                <span className="name-cell">
                  <ImageName kind={e.kind} previewUrl={e.preview_url} label={e.name} title={e.url ?? e.name} thumbnail={false} />
                  <DemoBadge demo={e.demo} />
                </span>
              </td>
              <td>{kindWithCapture(sourceKindLabel(e.kind), e.capture)}</td>
              <td>
                {e.size_bytes === null ? (
                  <span className="muted small" title={t('lib.sizeUnknownTitle')}>
                    {t('lib.sizeUnknown')}
                  </span>
                ) : (
                  formatBytes(e.size_bytes)
                )}
              </td>
              <td>{formatTime(e.deleted_at)}</td>
              <td title={formatTime(e.purge_at)}>{purgeIn(e.purge_at)}</td>
              <td className="actions-cell">
                <button type="button" className="link" disabled={busy} onClick={() => void restore(e)}>
                  {t('lib.restore')}
                </button>
                <button type="button" className="link danger" disabled={busy} onClick={() => void purge(e)}>
                  {t('lib.deleteForGood')}
                </button>
              </td>
            </tr>
          ))}
          {entries.length === 0 && !busy && (
            <tr>
              <td className="muted" colSpan={6}>
                {t('lib.trashEmpty')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  )
}
