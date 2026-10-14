import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { rag } from '../api/rag'
import type { AudioContent, Citation, Output, Source } from '../api/types'
import { MadeFrom } from './MadeFrom'
import { useAsync } from '../hooks/useAsync'
import { useTabStrip } from '../hooks/useTabStrip'
import { formatTime } from '../lib/format'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { optionsLabel, speakerName } from '../lib/outputOptions'
import { bestMatchIndex, flash, type LocateRequest } from '../lib/locate'
import { formFor } from '../lib/outputs'
import { OutputContent } from './outputs/OutputContent'
import { OutputProvenance } from './OutputProvenance'
import { checkSummary } from '../lib/outputProvenance'
import { t } from '../i18n'

interface Props {
  outputs: Output[]
  /** the notebook's uploads, to name what a document was made from */
  sources: Source[] | null
  selectedId: string | null
  onSelect: (id: string) => void
  onChanged: (o: Output) => void
  onDeleted: (id: string) => void
  onAskAbout: (o: Output) => void
  error: string | null
  /** the document over the whole window, the chat behind a toggle */
  fullView: boolean
  onFullView: (on: boolean) => void
  chatOpen: boolean
  onToggleChat: () => void
  style?: CSSProperties
  /** show this passage of the open document ("open document" on a citation) */
  locate?: LocateRequest | null
  /** "open in source" on a passage the document cites, as in the chat */
  onOpenSource: (c: Citation) => void
  /** the notebook's sources a passage can still point to; null while loading */
  presentSources: ReadonlySet<string> | null
}

/** The blocks a cited passage can be in, across the document renderers. */
const PASSAGE_BLOCKS = 'p, li, td, th, h1, h2, h3, h4, dt, dd, blockquote'

/** Right column, top: one tab per generated document, newest first, with
 *  the actions per document: ask about this, print, share, full view. */
export function OutputViewer({
  outputs,
  sources,
  selectedId,
  onSelect,
  onChanged,
  onDeleted,
  onAskAbout,
  error,
  fullView,
  onFullView,
  chatOpen,
  onToggleChat,
  style,
  locate,
  onOpenSource,
  presentSources,
}: Props) {
  const selected = outputs.find((o) => o.id === selectedId) ?? null
  const spec = useOutputOptions()
  const made = selected ? optionsLabel(selected.options, spec) : null
  const checked = checkSummary(selected?.provenance?.check)
  const { ref: tabsRef, onWheel: onTabsWheel, onKeyDown: onTabsKey } = useTabStrip(
    outputs.map((o) => o.id),
    selectedId,
    onSelect,
  )
  const enterButton = useRef<HTMLButtonElement>(null)
  const body = useRef<HTMLDivElement>(null)
  const selectedKind = selected?.kind
  const selectedReady = selected?.status === 'ready'

  // a located passage: the text block that matches the chunk best, scrolled
  // to and flashed; the mind map does its own (fit, then the node)
  useEffect(() => {
    if (!locate || !selectedReady || selectedKind === 'mindmap') return
    const frame = requestAnimationFrame(() => {
      const blocks = [...(body.current?.querySelectorAll<HTMLElement>(PASSAGE_BLOCKS) ?? [])]
      const i = bestMatchIndex(
        blocks.map((b) => b.textContent ?? ''),
        locate.text,
      )
      if (i >= 0) flash(blocks[i])
    })
    return () => cancelAnimationFrame(frame)
  }, [locate, selectedKind, selectedReady])
  const leaveButton = useRef<HTMLButtonElement>(null)
  const wasFull = useRef(fullView)

  // focus follows the mode: the × on entering, the full-view button on leaving
  useEffect(() => {
    if (fullView) leaveButton.current?.focus()
    else if (wasFull.current) enterButton.current?.focus()
    wasFull.current = fullView
  }, [fullView])
  const [shareOpen, setShareOpen] = useState(false)
  const { busy, error: actionError, run } = useAsync()

  async function share() {
    if (!selected) return
    const r = await run(() => rag.share(selected.id))
    if (r) onChanged({ ...selected, share_token: r.share_token })
  }
  async function unshare() {
    if (!selected) return
    const ok = await run(async () => {
      await rag.unshare(selected.id)
      return true
    })
    if (ok) onChanged({ ...selected, share_token: null })
  }
  async function remove() {
    if (!selected || !confirm(t('ws.deleteDoc', { title: selected.title || formFor(selected.kind).label }))) return
    const ok = await run(async () => {
      await rag.deleteOutput(selected.id)
      return true
    })
    if (ok) onDeleted(selected.id)
  }

  const shareUrl = selected?.share_token ? `${window.location.origin}/s/${selected.share_token}` : null
  const printable = selected ? formFor(selected.kind).printable && selected.status === 'ready' : false

  return (
    <section className="pane viewer" style={style}>
      {fullView && (
        <div className="full-bar no-print">
          <button type="button" className={chatOpen ? 'secondary small active' : 'secondary small'} aria-pressed={chatOpen} onClick={onToggleChat}>
            {t('viewer.chat')}
          </button>
          <button
            ref={leaveButton}
            type="button"
            className="icon"
            title={t('viewer.leaveFull')}
            aria-label={t('viewer.leaveFullLabel')}
            onClick={() => onFullView(false)}
          >
            ×
          </button>
        </div>
      )}
      <div className="tabs no-print" role="tablist" aria-label={t('viewer.documents')} ref={tabsRef} onWheel={onTabsWheel} onKeyDown={onTabsKey}>
        {outputs.map((o) => (
          <button
            key={o.id}
            type="button"
            role="tab"
            data-tab-id={o.id}
            tabIndex={o.id === selectedId || (!selectedId && o === outputs[0]) ? 0 : -1}
            aria-selected={o.id === selectedId}
            className={`tab status-${o.status}${o.id === selectedId ? ' active' : ''}`}
            onClick={() => onSelect(o.id)}
            title={`${formFor(o.kind).label} · ${formatTime(o.created_at)}`}
          >
            {o.title || formFor(o.kind).label}
            {(o.status === 'processing' || o.status === 'waiting') && <span className="spinner" aria-label={o.status} />}
          </button>
        ))}
        {outputs.length === 0 && <span className="muted">{t('viewer.noDocs')}</span>}
      </div>
      {(error || actionError) && <p className="error no-print">{error ?? actionError}</p>}
      <div className="viewer-body printable" ref={body}>
        {selected && (
          <>
            <header className="viewer-head">
              <h1 className="doc-title">{selected.title || formFor(selected.kind).label}</h1>
              <span className="badge">{formFor(selected.kind).label}</span>
              <span className="muted small">{formatTime(selected.created_at)}</span>
              {made && <span className="muted small" title={t('viewer.madeWith')}>{made}</span>}
              {checked && selected.provenance && (
                <span className="muted small check-line" title={t('outProv.checkTitle', { method: selected.provenance.check.method, threshold: selected.provenance.check.threshold })}>
                  {checked}
                </span>
              )}
              {selected.options?.sources?.length ? (
                <span className="muted small">
                  <MadeFrom ids={selected.options.sources} sources={sources} />
                </span>
              ) : null}
              <span className="actions no-print">
                <button type="button" className="link" disabled={selected.status !== 'ready'} onClick={() => onAskAbout(selected)}>
                  {t('viewer.askAbout')}
                </button>
                <button type="button" className="link" disabled={!printable} onClick={() => window.print()}>
                  {t('viewer.print')}
                </button>
                <button type="button" className="link" disabled={selected.status !== 'ready'} onClick={() => setShareOpen((v) => !v)}>
                  {selected.share_token ? t('viewer.shared') : t('viewer.share')}
                </button>
                {!fullView && (
                  <button ref={enterButton} type="button" className="link" onClick={() => onFullView(true)}>
                    {t('viewer.fullView')}
                  </button>
                )}
                <button type="button" className="link danger" disabled={busy} onClick={() => void remove()}>
                  {t('common.delete')}
                </button>
              </span>
            </header>
            {shareOpen && (
              <div className="share card no-print">
                {shareUrl ? (
                  <>
                    <p className="small">{t('viewer.shareInfo')}</p>
                    <div className="row">
                      <input readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} />
                      <button type="button" className="secondary" onClick={() => void navigator.clipboard?.writeText(shareUrl)}>
                        {t('viewer.copy')}
                      </button>
                      <button type="button" className="secondary" disabled={busy} onClick={() => void unshare()}>
                        {t('viewer.revoke')}
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="row">
                    <p className="small">{t('viewer.shareCreateInfo')}</p>
                    <button type="button" disabled={busy} onClick={() => void share()}>
                      {t('viewer.createLink')}
                    </button>
                  </div>
                )}
              </div>
            )}
            <OutputProvenance key={selected.id} output={selected} provenance={selected.provenance} presentSources={presentSources} onOpenSource={onOpenSource}>
              <OutputContent
                kind={selected.kind}
                locate={locate ?? null}
                title={selected.title}
                status={selected.status}
                error={selected.error}
                content={selected.content}
                onExpired={() => rag.getOutput(selected.id).then((o) => (o.content as AudioContent).url)}
                speakerName={(s) => speakerName(s, selected.options, spec)}
              />
            </OutputProvenance>
          </>
        )}
      </div>
    </section>
  )
}
