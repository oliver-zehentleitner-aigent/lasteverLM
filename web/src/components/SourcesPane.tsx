import { useEffect, useMemo, useRef, useState } from 'react'
import { ingest } from '../api/ingest'
import type { Source } from '../api/types'
import { SOURCE_POLL_INTERVAL_MS } from '../config'
import { useAsync } from '../hooks/useAsync'
import { sourceKindLabel, uploadedSources } from '../lib/outputs'
import { audioFiles } from '../lib/openEntry'
import { AudioCheck, PlayButton } from './AudioCheck'
import { StarterBadge } from './StarterBadge'
import { StatusBadge } from './PendingReason'
import { t } from '../i18n'
import { priceLabel } from '../lib/estimate'
import { whenLabel } from '../lib/outputsList'
import { IconTrash } from './Icons'
import { readsFinished, requestBalanceRefresh, useBalanceActivity } from '../lib/balance'

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
  /** a click on a source's name opens it as a tab in the viewer */
  onOpen: (source: Source) => void
}

/** Left column, top: the sources with status and delete; the add button
 *  opens the wizard. The list polls while any source is still processing
 *  (the contract has no push channel) and stops when everything is ready
 *  or failed. Only uploads are listed: generated documents are sources of
 *  kind `generated` for the chat, but the Outputs list shows them. */
export function SourcesPane({ notebookId, highlightedSourceId, version, onAdd, excluded, onToggle, onAll, ownGenerated, onSourcesChange, onOpen }: Props) {
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
  // reading is paid work: the balance follows while it runs and when a read ends
  useBalanceActivity(processing)
  const lastSources = useRef(sources)
  useEffect(() => {
    lastSources.current = sources
  }, [sources])
  useEffect(() => {
    if (!processing) return
    const t = setInterval(() => {
      ingest.listSources(notebookId).then((list) => {
        if (readsFinished(lastSources.current, list)) requestBalanceRefresh()
        setSources(list)
      }, () => {
        // a failed poll is retried on the next tick; user actions surface errors through run()
      })
    }, SOURCE_POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [processing, notebookId])

  const reload = async () => setSources(await ingest.listSources(notebookId))

  /** "read now" on an unread source: its price first, then ingest reads it. */
  async function readNow(s: Source) {
    const lib = s.library_id ?? s.id
    const est = await run(() => ingest.readEstimate([lib]))
    const item = est?.items.find((x) => x.library_id === lib) ?? est?.items[0]
    if (!est) return
    const price = item ? priceLabel({ charge_cents_min: item.charge_cents_min, charge_cents_max: item.charge_cents_max }) : null
    if (!confirm(t('sources.readNowConfirm', { name: s.name, price: price ?? '—', basis: item?.basis ?? '' }))) return
    await run(async () => {
      await ingest.processSources([lib])
      await reload()
    })
  }

  /** "fetch again" on a web page: read again only when it changed. */
  async function fetchAgain(s: Source) {
    if (!confirm(t('sources.fetchAgainConfirm', { name: s.name }))) return
    await run(async () => {
      await ingest.refetchSource(s.id)
      await reload()
    })
  }

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
            <span className="src-name">
              <button type="button" className="link name" title={t('sources.openTitle', { name: s.name })} onClick={() => onOpen(s)}>
                {s.name}
              </button>
              <StarterBadge item={s} />
              {s.kind === 'url' && s.fetched_at && <span className="src-fetched muted small">{t('sources.fetchedShort', { when: whenLabel(s.fetched_at) })}</span>}
            </span>
            {/* one group that never wraps inside: kind, capture, status, play, remove */}
            <span className="src-badges">
              <span className="badge kind" title={sourceKindLabel(s.kind)}>
                <span className="long">{sourceKindLabel(s.kind)}</span>
                <span className="short">{t(`kindShort.${s.kind}`)}</span>
              </span>
              {s.capture && (
                <span className="badge capture" title={t('sources.captureTitle')}>
                  {t(`capture.${s.capture}`)}
                </span>
              )}
              <StatusBadge status={s.status} error={s.error} />
              {s.kind === 'url' && (s.version ?? 1) > 1 && (
                <span className="badge" title={t('sources.versionTitle', { n: s.version! })}>
                  {t('sources.version', { n: s.version! })}
                </span>
              )}
              {s.status === 'added' && (
                <button type="button" className="link small" disabled={busy} title={t('sources.readNowTitle')} onClick={() => void readNow(s)}>
                  {t('sources.readNow')}
                </button>
              )}
              {s.kind === 'url' && s.status !== 'added' && s.status !== 'processing' && (
                <button
                  type="button"
                  className="icon"
                  disabled={busy}
                  title={s.fetched_at ? `${t('sources.fetched', { when: whenLabel(s.fetched_at) })} · ${t('sources.fetchAgainTitle')}` : t('sources.fetchAgainTitle')}
                  aria-label={t('sources.fetchAgain')}
                  onClick={() => void fetchAgain(s)}
                >
                  ↻
                </button>
              )}
              {audioFiles(s) && <PlayButton open={playing?.id === s.id} name={s.name} onToggle={() => togglePlayer(s)} />}
              <button type="button" className="icon icon-danger" title={t('sources.remove')} aria-label={t('sources.removeNamed', { name: s.name })} onClick={() => void remove(s)}>
                <IconTrash />
              </button>
            </span>
            {playing?.id === s.id && (
              <div className="src-player">
                <AudioCheck files={playing.files} />
              </div>
            )}
          </li>
        ))}
        {shown.length === 0 && !busy && <li className="muted">{t('sources.none')}</li>}
      </ul>
    </section>
  )
}
