import { useEffect, useState } from 'react'
import { ingest } from '../api/ingest'
import { SOURCE_POLL_INTERVAL_MS } from '../config'
import type { LibraryEntry, TrashEntry } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { formatBytes, formatTime } from '../lib/format'
import { kindWithCapture } from '../lib/capture'
import { bulkDeleteConfirmText, deleteConfirmText, filterLibrary, notebookTitleFrom, purgeIn, type LibraryFilter } from '../lib/library'
import { openTarget } from '../lib/openEntry'
import { SOURCE_FORMS } from '../lib/outputs'
import { DemoBadge } from './DemoBadge'
import { ImageName } from './ImageName'
import { t, tn } from '../i18n'

interface Props {
  onOpenNotebook: (id: string) => void
  /** the settings page, at the trash-days field */
  onOpenSettings: () => void
}

/** /library: every upload and URL of the user with the notebooks it is in,
 *  and the trash. Removing a source in a notebook only detaches it;
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
            {v === 'library' ? t('lib.sources') : t('lib.trash')}
          </a>
        ))}
      </nav>
      {view === 'library' ? <LibraryList onOpenNotebook={onOpenNotebook} /> : <TrashList onOpenSettings={onOpenSettings} />}
    </main>
  )
}

function LibraryList({ onOpenNotebook }: Pick<Props, 'onOpenNotebook'>) {
  const [entries, setEntries] = useState<LibraryEntry[]>([])
  const [filter, setFilter] = useState<LibraryFilter>({ kind: 'all', query: '' })
  // ticked rows, kept across filtering; actions apply to those still listed
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [progress, setProgress] = useState<{ kind: 'delete' | 'add'; done: number; total: number } | null>(null)
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => setEntries(await ingest.listLibrary()))
  }, [run])

  // new entries (a new account's demo sources, say) turn ready as the worker gets to them
  const processing = entries.some((e) => e.status === 'processing')
  useEffect(() => {
    if (!processing) return
    const timer = setInterval(() => {
      ingest.listLibrary().then(setEntries, () => {
        // a failed poll is retried on the next tick
      })
    }, SOURCE_POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [processing])

  async function remove(e: LibraryEntry) {
    if (!confirm(deleteConfirmText(e))) return
    const ok = await run(async () => {
      await ingest.deleteLibraryEntry(e.id)
      return true
    })
    if (ok) setEntries((prev) => prev.filter((x) => x.id !== e.id))
  }

  const shown = filterLibrary(entries, filter)
  const selected = entries.filter((e) => picked.has(e.id))
  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  /** One DELETE per entry, in order; after a failure the rest stays ticked. */
  async function removeSelected() {
    if (selected.length === 0 || !confirm(bulkDeleteConfirmText(selected))) return
    await run(async () => {
      let done = 0
      setProgress({ kind: 'delete', done, total: selected.length })
      try {
        for (const e of selected) {
          await ingest.deleteLibraryEntry(e.id)
          done += 1
          setProgress({ kind: 'delete', done, total: selected.length })
          setEntries((prev) => prev.filter((x) => x.id !== e.id))
          setPicked((prev) => {
            const next = new Set(prev)
            next.delete(e.id)
            return next
          })
        }
      } finally {
        setProgress(null)
      }
    })
  }

  /** A notebook named after the first entry (editable), the entries added
   *  to it one by one, then opened. */
  async function notebookFromSelected() {
    if (selected.length === 0) return
    const title = prompt(t('lib.notebookTitlePrompt'), notebookTitleFrom(selected))?.trim()
    if (!title) return
    const id = await run(async () => {
      const nb = await ingest.createNotebook(title)
      let done = 0
      setProgress({ kind: 'add', done, total: selected.length })
      try {
        for (const e of selected) {
          await ingest.addFromLibrary(nb.id, e.id)
          done += 1
          setProgress({ kind: 'add', done, total: selected.length })
        }
      } finally {
        setProgress(null)
      }
      return nb.id
    })
    if (id) onOpenNotebook(id)
  }

  return (
    <>
      <p className="muted small">
        {t('lib.intro')}
      </p>
      <div className="filters">
        <label>
          {t('lib.kind')}
          <select value={filter.kind} onChange={(e) => setFilter({ ...filter, kind: e.target.value as LibraryFilter['kind'] })}>
            <option value="all">{t('lib.all')}</option>
            {SOURCE_FORMS.map((f) => (
              <option key={f.kind} value={f.kind}>
                {f.label}
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
      {selected.length > 0 && (
        <div className="selection-bar" role="region" aria-label={tn('lib.selected', selected.length)}>
          <span className="muted small">{progress ? t(progress.kind === 'delete' ? 'lib.progressDelete' : 'lib.progressAdd', { done: progress.done, total: progress.total }) : tn('lib.selected', selected.length)}</span>
          <button type="button" className="secondary" disabled={busy} onClick={() => void notebookFromSelected()}>
            {tn('lib.notebookFromN', selected.length)}
          </button>
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
            const href = openTarget(e)
            return (
              <tr key={e.id} className={picked.has(e.id) ? 'picked' : undefined}>
                <td className="pick-col">
                  <input type="checkbox" checked={picked.has(e.id)} onChange={() => toggle(e.id)} aria-label={t('lib.selectRow', { name: e.name })} />
                </td>
                <td className="name">
                  <span className="name-cell">
                    {href ? (
                      <a className="open-name" href={href} target="_blank" rel="noopener noreferrer" title={t('lib.openTitle', { name: e.name })}>
                        <ImageName previewUrl={e.preview_url} label={e.name} title={e.url ?? e.name} />
                      </a>
                    ) : (
                      <ImageName previewUrl={e.preview_url} label={e.name} title={e.url ?? e.name} />
                    )}
                    <DemoBadge demo={e.demo} />
                  </span>
                </td>
                <td>{kindWithCapture(SOURCE_FORMS.find((f) => f.kind === e.kind)?.label ?? e.kind, e.capture)}</td>
                <td>
                  <span className={`badge ${e.status}`}>{t(`status.${e.status}`)}</span>
                  {e.status === 'failed' && e.error && <span className="error small"> {e.error}</span>}
                </td>
                <td>
                  {e.size_bytes === null ? (
                    <span className="muted small" title={t('lib.sizeUnknownTitle')}>
                      {t('lib.sizeUnknown')}
                    </span>
                  ) : (
                    formatBytes(e.size_bytes)
                  )}
                </td>
                <td>{formatTime(e.created_at)}</td>
                <td>
                  {e.notebooks.length === 0 ? (
                    <span className="muted small">{t('lib.notInAny')}</span>
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
                  {href ? (
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

/** Deleted entries until they are purged: restore puts one back in the
 *  library (in no notebook), delete removes it for good. */
function TrashList({ onOpenSettings }: Pick<Props, 'onOpenSettings'>) {
  const [entries, setEntries] = useState<TrashEntry[]>([])
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => setEntries(await ingest.listTrash()))
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
                  <ImageName previewUrl={e.preview_url} label={e.name} title={e.url ?? e.name} />
                  <DemoBadge demo={e.demo} />
                </span>
              </td>
              <td>{kindWithCapture(SOURCE_FORMS.find((f) => f.kind === e.kind)?.label ?? e.kind, e.capture)}</td>
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
