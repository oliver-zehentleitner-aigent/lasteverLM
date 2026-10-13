import { useEffect, useState } from 'react'
import { ingest } from '../api/ingest'
import type { LibraryEntry, TrashEntry } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { formatBytes, formatTime } from '../lib/format'
import { kindWithCapture } from '../lib/capture'
import { deleteConfirmText, filterLibrary, purgeIn, type LibraryFilter } from '../lib/library'
import { SOURCE_FORMS } from '../lib/outputs'
import { t } from '../i18n'

interface Props {
  onOpenNotebook: (id: string) => void
}

/** /library: every upload and URL of the user with the notebooks it is in,
 *  and the trash. Removing a source in a notebook only detaches it;
 *  deleting here moves it to the trash (out of every notebook, after a
 *  confirmation that names them), from where it is restored or purged. */
export function LibraryPage({ onOpenNotebook }: Props) {
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
      {view === 'library' ? <LibraryList onOpenNotebook={onOpenNotebook} /> : <TrashList />}
    </main>
  )
}

function LibraryList({ onOpenNotebook }: Props) {
  const [entries, setEntries] = useState<LibraryEntry[]>([])
  const [filter, setFilter] = useState<LibraryFilter>({ kind: 'all', query: '' })
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => setEntries(await ingest.listLibrary()))
  }, [run])

  async function remove(e: LibraryEntry) {
    if (!confirm(deleteConfirmText(e))) return
    const ok = await run(async () => {
      await ingest.deleteLibraryEntry(e.id)
      return true
    })
    if (ok) setEntries((prev) => prev.filter((x) => x.id !== e.id))
  }

  const shown = filterLibrary(entries, filter)

  return (
    <>
      <p className="muted small">
        {t('lib.intro')}
      </p>
      <div className="row filters">
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
      <table>
        <thead>
          <tr>
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
          {shown.map((e) => (
            <tr key={e.id}>
              <td className="name" title={e.url ?? e.name}>
                {e.name}
              </td>
              <td>{kindWithCapture(SOURCE_FORMS.find((f) => f.kind === e.kind)?.label ?? e.kind, e.capture)}</td>
              <td>
                <span className={`badge ${e.status}`}>{t(`status.${e.status}`)}</span>
                {e.status === 'failed' && e.error && <span className="error small"> {e.error}</span>}
              </td>
              <td>{e.size_bytes === null ? '—' : formatBytes(e.size_bytes)}</td>
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
              <td>
                <button type="button" className="link danger" disabled={busy} onClick={() => void remove(e)}>
                  {t('common.delete')}
                </button>
              </td>
            </tr>
          ))}
          {shown.length === 0 && !busy && (
            <tr>
              <td className="muted" colSpan={7}>
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
function TrashList() {
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
        {t('lib.trashIntro')}
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
              <td className="name" title={e.url ?? e.name}>
                {e.name}
              </td>
              <td>{kindWithCapture(SOURCE_FORMS.find((f) => f.kind === e.kind)?.label ?? e.kind, e.capture)}</td>
              <td>{e.size_bytes === null ? '—' : formatBytes(e.size_bytes)}</td>
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
