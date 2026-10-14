import { useEffect, useState } from 'react'
import { ingest } from '../api/ingest'
import type { Source } from '../api/types'
import { SOURCE_POLL_INTERVAL_MS } from '../config'
import { useAsync } from '../hooks/useAsync'
import { SOURCE_FORMS, uploadedSources } from '../lib/outputs'
import { DemoBadge } from './DemoBadge'
import { t } from '../i18n'

interface Props {
  notebookId: string
  highlightedSourceId: string | null
  /** bumps when the wizard added sources, to reload the list */
  version: number
  onAdd: () => void
  /** the sources turned off for the chat and new documents */
  excluded: ReadonlySet<string>
  onToggle: (id: string) => void
  /** all on (true) or all off (false) */
  onAll: (on: boolean) => void
  /** the uploads once loaded, for the Create button and removed citations */
  onSourcesChange: (sources: Source[]) => void
}

/** Left column, top: the sources with status and delete; the add button
 *  opens the wizard. The list polls while any source is still processing
 *  (the contract has no push channel) and stops when everything is ready
 *  or failed. Only uploads are listed: generated documents are sources of
 *  kind `generated` for the chat, but the Outputs list shows them. */
export function SourcesPane({ notebookId, highlightedSourceId, version, onAdd, excluded, onToggle, onAll, onSourcesChange }: Props) {
  const [sources, setSources] = useState<Source[]>([])
  const [loaded, setLoaded] = useState(false)
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => {
      setSources(uploadedSources(await ingest.listSources(notebookId)))
      setLoaded(true)
    })
  }, [notebookId, version, run])

  useEffect(() => {
    if (loaded) onSourcesChange(sources)
  }, [loaded, sources, onSourcesChange])

  const processing = sources.some((s) => s.status === 'processing')
  useEffect(() => {
    if (!processing) return
    const t = setInterval(() => {
      ingest.listSources(notebookId).then((list) => setSources(uploadedSources(list)), () => {
        // a failed poll is retried on the next tick; user actions surface errors through run()
      })
    }, SOURCE_POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [processing, notebookId])

  async function remove(s: Source) {
    if (!confirm(t('sources.removeConfirm', { name: s.name }))) return
    const ok = await run(async () => {
      await ingest.deleteSource(s.id)
      return true
    })
    if (ok) setSources((prev) => prev.filter((x) => x.id !== s.id))
  }

  return (
    <section className="pane sources">
      <div className="row head">
        <h2>{t('sources.title')}</h2>
        {sources.length > 1 && (
          <span className="source-all">
            <button type="button" className="link small" onClick={() => onAll(true)} disabled={excluded.size === 0}>
              {t('sources.selectAll')}
            </button>
            <span className="muted small">/</span>
            <button type="button" className="link small" onClick={() => onAll(false)} disabled={sources.every((s) => excluded.has(s.id))}>
              {t('sources.selectNone')}
            </button>
          </span>
        )}
        <button type="button" className="secondary small" onClick={onAdd}>
          {t('sources.add')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <ul className="list">
        {sources.map((s) => (
          <li
            key={s.id}
            id={`source-${s.id}`}
            className={[s.id === highlightedSourceId ? 'highlight' : '', `status-${s.status}`, excluded.has(s.id) ? 'off' : ''].join(' ')}
          >
            <input
              type="checkbox"
              className="source-check"
              checked={!excluded.has(s.id)}
              onChange={() => onToggle(s.id)}
              aria-label={t('sources.use', { name: s.name })}
              title={t('sources.useTitle')}
            />
            <div className="item">
              <span className="name" title={s.name}>
                {s.name}
              </span>
              <DemoBadge demo={s.demo} />
              <span className="badge">{SOURCE_FORMS.find((f) => f.kind === s.kind)?.label ?? s.kind}</span>
              {s.capture && (
                <span className="badge" title={t('sources.captureTitle')}>
                  {t(`capture.${s.capture}`)}
                </span>
              )}
              <span className={`badge ${s.status}`}>{t(`status.${s.status}`)}</span>
              {s.status === 'failed' && s.error && <span className="error small">{s.error}</span>}
              {s.status === 'processing' && s.error && <span className="muted small">{t('sources.retrying', { error: s.error })}</span>}
            </div>
            <button type="button" className="icon" title={t('sources.remove')} onClick={() => void remove(s)}>
              ×
            </button>
          </li>
        ))}
        {sources.length === 0 && !busy && <li className="muted">{t('sources.none')}</li>}
      </ul>
    </section>
  )
}
