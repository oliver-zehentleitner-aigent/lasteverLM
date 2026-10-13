import { useEffect, useState } from 'react'
import { ingest } from '../api/ingest'
import type { Source } from '../api/types'
import { SOURCE_POLL_INTERVAL_MS } from '../config'
import { useAsync } from '../hooks/useAsync'

interface Props {
  notebookId: string
  highlightedSourceId: string | null
  /** bumps when the wizard added sources, to reload the list */
  version: number
  onAdd: () => void
}

/** Left column, top: the sources with status and delete; the add button
 *  opens the wizard. The list polls while any source is still processing
 *  (the contract has no push channel) and stops when everything is ready
 *  or failed. Generated documents appear here too, as sources of kind
 *  `generated`, because the chat can cite them. */
export function SourcesPane({ notebookId, highlightedSourceId, version, onAdd }: Props) {
  const [sources, setSources] = useState<Source[]>([])
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => setSources(await ingest.listSources(notebookId)))
  }, [notebookId, version, run])

  const processing = sources.some((s) => s.status === 'processing')
  useEffect(() => {
    if (!processing) return
    const t = setInterval(() => {
      ingest.listSources(notebookId).then(setSources, () => {
        // a failed poll is retried on the next tick; user actions surface errors through run()
      })
    }, SOURCE_POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [processing, notebookId])

  async function remove(s: Source) {
    if (!confirm(`Remove "${s.name}"?`)) return
    const ok = await run(async () => {
      await ingest.deleteSource(s.id)
      return true
    })
    if (ok) setSources((prev) => prev.filter((x) => x.id !== s.id))
  }

  return (
    <section className="pane sources">
      <div className="row head">
        <h2>Sources</h2>
        <button type="button" className="secondary small" onClick={onAdd}>
          + add
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <ul className="list">
        {sources.map((s) => (
          <li
            key={s.id}
            id={`source-${s.id}`}
            className={[s.id === highlightedSourceId ? 'highlight' : '', `status-${s.status}`].join(' ')}
          >
            <div className="item">
              <span className="name" title={s.name}>
                {s.name}
              </span>
              <span className={`badge ${s.status}`}>{s.kind === 'generated' ? 'generated' : s.status}</span>
              {s.status === 'failed' && s.error && <span className="error small">{s.error}</span>}
              {s.status === 'processing' && s.error && <span className="muted small">Retrying after: {s.error}</span>}
            </div>
            <button type="button" className="icon" title="Remove source" onClick={() => void remove(s)}>
              ×
            </button>
          </li>
        ))}
        {sources.length === 0 && !busy && <li className="muted">No sources yet. Add a PDF, a text, a web page or an image.</li>}
      </ul>
    </section>
  )
}
