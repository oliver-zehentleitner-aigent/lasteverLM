import { useEffect, useState } from 'react'
import { ingest } from '../api/ingest'
import type { LibraryEntry } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { formatBytes, formatTime } from '../lib/format'
import { deleteConfirmText, filterLibrary, type LibraryFilter } from '../lib/library'
import { SOURCE_FORMS } from '../lib/outputs'

interface Props {
  onOpenNotebook: (id: string) => void
}

/** /library: every upload and URL of the user with the notebooks it is in.
 *  Removing a source in a notebook only detaches it; deleting here removes
 *  it from every notebook, after a confirmation that names them. */
export function LibraryPage({ onOpenNotebook }: Props) {
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
    <main className="library">
      <h1>Library</h1>
      <p className="muted small">
        Everything you uploaded or linked, once, and the notebooks it is in. Generated documents live in their notebook.
      </p>
      <div className="row filters">
        <label>
          Kind
          <select value={filter.kind} onChange={(e) => setFilter({ ...filter, kind: e.target.value as LibraryFilter['kind'] })}>
            <option value="all">All</option>
            {SOURCE_FORMS.map((f) => (
              <option key={f.kind} value={f.kind}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Name
          <input type="search" value={filter.query} placeholder="part of a name or address" onChange={(e) => setFilter({ ...filter, query: e.target.value })} />
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Kind</th>
            <th>Status</th>
            <th>Size</th>
            <th>Added</th>
            <th>In notebooks</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {shown.map((e) => (
            <tr key={e.id}>
              <td className="name" title={e.url ?? e.name}>
                {e.name}
              </td>
              <td>{SOURCE_FORMS.find((f) => f.kind === e.kind)?.label ?? e.kind}</td>
              <td>
                <span className={`badge ${e.status}`}>{e.status}</span>
                {e.status === 'failed' && e.error && <span className="error small"> {e.error}</span>}
              </td>
              <td>{e.size_bytes === null ? '—' : formatBytes(e.size_bytes)}</td>
              <td>{formatTime(e.created_at)}</td>
              <td>
                {e.notebooks.length === 0 ? (
                  <span className="muted small">not in any notebook</span>
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
                  delete
                </button>
              </td>
            </tr>
          ))}
          {shown.length === 0 && !busy && (
            <tr>
              <td className="muted" colSpan={7}>
                {entries.length === 0 ? 'Nothing yet. Sources you add to a notebook appear here.' : 'Nothing matches the filter.'}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  )
}
