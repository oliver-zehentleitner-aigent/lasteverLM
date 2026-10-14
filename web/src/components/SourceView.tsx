import { useState } from 'react'
import type { Source } from '../api/types'
import { t } from '../i18n'
import { formatTime } from '../lib/format'
import { citationTarget, openTarget } from '../lib/openEntry'
import { sourceKindLabel } from '../lib/outputs'
import { defaultView, type SourceViewMode, type ViewerTab } from '../lib/viewerTabs'
import { SourceRead } from './SourceRead'
import { SourceText } from './SourceText'
import { SourceUnread } from './SourceUnread'
import { StarterBadge } from './StarterBadge'

/** A source as a viewer tab: its head (name, kind, the Original | As read
 *  switch, a small link that opens it in a new browser tab) and one of two
 *  views. Original shows the thing itself: an image inline, audio in a
 *  player, a PDF in the browser's viewer (on the cited page when a
 *  citation opened it), a web page as its address. As read shows the text
 *  the system extracted, chunk by chunk, the cited chunk marked. */
export function SourceView({ source, tab, onRead }: { source: Source; tab: ViewerTab; onRead: () => void }) {
  const [mode, setMode] = useState<SourceViewMode>(() => defaultView(source.kind))
  // the address the tab holds, not the list's newest: a new presigned src would load the file again
  // a web page holds its snapshot's address, any other source its file's
  const held = source.kind === 'url' ? { ...source, snapshot_url: tab.url ?? source.snapshot_url } : { ...source, preview_url: tab.url ?? source.preview_url }
  const external = citationTarget(held, tab.page ?? null)
  return (
    <>
      <header className="viewer-head">
        <h1 className="doc-title">{source.name}</h1>
        <span className="badge">{sourceKindLabel(source.kind)}</span>
        <StarterBadge item={source} />
        <span className="presets source-mode" role="radiogroup" aria-label={t('srcView.mode')}>
          {(['original', 'read'] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={mode === m} className={mode === m ? 'preset active' : 'preset'} onClick={() => setMode(m)}>
              {t(`srcView.${m}`)}
            </button>
          ))}
        </span>
        {external && (
          <a className="icon-link no-print" href={external} target="_blank" rel="noopener noreferrer" title={t('srcView.newTab')} aria-label={t('srcView.newTab')}>
            ↗
          </a>
        )}
      </header>
      {mode === 'original' ? (
        <Original source={held} page={tab.page ?? null} nonce={tab.nonce ?? 0} />
      ) : source.status === 'added' ? (
        // not read yet: nothing to show as read, the way to read it
        <SourceUnread source={source} onRead={onRead} />
      ) : (
        <SourceRead key={`${source.id}:${tab.nonce ?? 0}`} sourceId={source.id} chunkId={tab.chunkId ?? null} chunkIndex={tab.chunkIndex ?? null} />
      )}
    </>
  )
}

function Original({ source, page, nonce }: { source: Source; page: number | null; nonce: number }) {
  // text and Markdown inline, from ingest, also before the source is read
  if (source.kind === 'text') return <SourceText source={source} />
  const href = openTarget({ kind: source.kind, url: source.kind === 'url' ? (source.preview_url ?? null) : null, preview_url: source.preview_url })
  if (!href) return <p className="muted">{t('srcView.noOriginal')}</p>
  switch (source.kind) {
    case 'image':
      return <img className="source-image" src={href} alt={source.name} />
    case 'audio':
      return <audio className="source-audio" controls preload="metadata" src={href} />
    case 'pdf':
      // keyed by the open, so a citation's page loads even when the tab was open
      return <iframe key={nonce} className="source-frame" src={citationTarget(source, page) ?? href} title={source.name} />
    case 'url':
      return <PageSnapshot source={source} live={href} />
    default:
      return (
        <p>
          <a href={href} target="_blank" rel="noopener noreferrer">
            {t('srcView.openFile')}
          </a>
        </p>
      )
  }
}

/** A web page's Original: the snapshot of the version that was read, in a
 *  sandboxed iframe (no scripts, no same origin; links may open in a new
 *  tab), with a line saying when and which version, and the live page.
 *  Without a snapshot yet, the address alone. */
function PageSnapshot({ source, live }: { source: Source; live: string }) {
  const liveUrl = source.final_url ?? live
  const head = (
    <p className="snapshot-head muted small">
      {source.snapshot_url && source.fetched_at
        ? t('srcView.snapshot', { when: formatTime(source.fetched_at), version: source.version ?? 1 })
        : t('srcView.noSnapshot')}
      {' · '}
      <a href={liveUrl} target="_blank" rel="noopener noreferrer">
        {t('srcView.livePage')} ↗
      </a>
    </p>
  )
  if (!source.snapshot_url) return head
  return (
    <>
      {head}
      <iframe className="source-frame snapshot" src={source.snapshot_url} title={t('srcView.snapshotTitle', { name: source.name })} sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" />
    </>
  )
}
