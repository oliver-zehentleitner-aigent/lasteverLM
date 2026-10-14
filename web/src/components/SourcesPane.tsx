import { useEffect, useMemo, useState } from 'react'
import { ingest } from '../api/ingest'
import { RedeemLink } from './RedeemLink'
import type { Source } from '../api/types'
import { SOURCE_POLL_INTERVAL_MS } from '../config'
import { useAsync } from '../hooks/useAsync'
import { sourceKindLabel, uploadedSources } from '../lib/outputs'
import { audioFiles } from '../lib/openEntry'
import { AudioCheck, PlayButton } from './AudioCheck'
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
  /** the source ids of this notebook's own documents (listed under Outputs); null while loading */
  ownGenerated: ReadonlySet<string> | null
  onSourcesChange: (sources: Source[]) => void
}

/** Left column, top: the sources with status and delete; the add button
 *  opens the wizard. The list polls while any source is still processing
 *  (the contract has no push channel) and stops when everything is ready
 *  or failed. Only uploads are listed: generated documents are sources of
 *  kind `generated` for the chat, but the Outputs list shows them. */
export function SourcesPane({ notebookId, highlightedSourceId, version, onAdd, excluded, onToggle, onAll, ownGenerated, onSourcesChange }: Props) {
  const [sources, setSources] = useState<Source[]>([])
  const [loaded, setLoaded] = useState(false)
  const { busy, error, run } = useAsync()
  // the one audio source whose player is open, with the files taken then
  const [playing, setPlaying] = useState<{ id: string; files: NonNullable<ReturnType<typeof audioFiles>> } | null>(null)

  function togglePlayer(s: Source) {
    const files = audioFiles(s)
    setPlaying((p) => (p?.id === s.id || !files ? null : { id: s.id, files }))
  }

  useEffect(() => {
    void run(async () => {
      setSources(await ingest.listSources(notebookId))
      setLoaded(true)
    })
  }, [notebookId, version, run])

  // every source of the notebook as listed; shown are the uploads and the documents added from the library
  const shown = useMemo(() => uploadedSources(sources, ownGenerated), [sources, ownGenerated])

  useEffect(() => {
    if (loaded) onSourcesChange(shown)
  }, [loaded, shown, onSourcesChange])

  // a source waiting for credit starts once a voucher is redeemed: keep polling for it too
  const processing = sources.some((s) => s.status === 'processing' || s.status === 'waiting_for_credit')
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
        {shown.length > 1 && (
          <span className="source-all">
            <button type="button" className="link small" onClick={() => onAll(true)} disabled={excluded.size === 0}>
              {t('sources.selectAll')}
            </button>
            <span className="muted small">/</span>
            <button type="button" className="link small" onClick={() => onAll(false)} disabled={shown.every((s) => excluded.has(s.id))}>
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
        {shown.map((s) => (
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
              <span className="badge">{sourceKindLabel(s.kind)}</span>
              {s.capture && (
                <span className="badge" title={t('sources.captureTitle')}>
                  {t(`capture.${s.capture}`)}
                </span>
              )}
              <span className={`badge ${s.status}`}>{t(`status.${s.status}`)}</span>
              {audioFiles(s) && <PlayButton open={playing?.id === s.id} name={s.name} onToggle={() => togglePlayer(s)} />}
              {s.status === 'failed' && s.error && <span className="error small">{s.error}</span>}
              {s.status === 'processing' && s.error && <span className="muted small">{t('sources.retrying', { error: s.error })}</span>}
              {s.status === 'waiting_for_credit' && <RedeemLink />}
              {playing?.id === s.id && <AudioCheck files={playing.files} />}
            </div>
            <button type="button" className="icon" title={t('sources.remove')} onClick={() => void remove(s)}>
              ×
            </button>
          </li>
        ))}
        {shown.length === 0 && !busy && <li className="muted">{t('sources.none')}</li>}
      </ul>
    </section>
  )
}
