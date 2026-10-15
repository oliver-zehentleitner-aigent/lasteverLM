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
import { formFor, sourceKindLabel } from '../lib/outputs'
import { tabKey, type ViewerTab } from '../lib/viewerTabs'
import { SourceView } from './SourceView'
import { OutputContent } from './outputs/OutputContent'
import { ShareCard } from './ShareCard'
import { OutputProvenance } from './OutputProvenance'
import { checkSummary } from '../lib/outputProvenance'
import { judgeHead } from '../lib/judge'
import { JudgeRequest } from './JudgeRequest'
import { t } from '../i18n'
import { renamedTitle } from '../lib/conversations'
import { InlineRename } from './InlineRename'

interface Props {
  outputs: Output[]
  /** the notebook's uploads, to name what a document was made from and to show an opened source */
  sources: Source[] | null
  /** what the user opened, in the order opened; the lists stay the index */
  tabs: ViewerTab[]
  activeKey: string | null
  onActivate: (key: string) => void
  onClose: (key: string) => void
  /** a source tab's "read now" started reading: the Sources list reloads */
  onSourcesChanged: () => void
  onChanged: (o: Output) => void
  /** a double-click (or F2) on a tab renames the output */
  onRename: (o: Output, title: string) => void
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

/** Right column, top: one tab per output or source the user opened, in
 *  the order opened, each closable. An output shows its document with the
 *  actions (ask about this, print, share, full view); a source its
 *  Original or As read view. */
export function OutputViewer({
  outputs,
  sources,
  tabs,
  activeKey,
  onActivate,
  onClose,
  onSourcesChanged,
  onChanged,
  onRename,
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
  // a tab whose output or source is not (yet) in its list is left out
  const shown = tabs.flatMap((tab) => {
    const output = tab.type === 'output' ? outputs.find((o) => o.id === tab.id) : undefined
    const source = tab.type === 'source' ? sources?.find((s) => s.id === tab.id) : undefined
    return output || source ? [{ tab, key: tabKey(tab), output, source }] : []
  })
  const active = shown.find((x) => x.key === activeKey) ?? null
  const selected = active?.output ?? null
  const spec = useOutputOptions()
  const made = selected ? optionsLabel(selected.options, spec) : null
  const checked = checkSummary(selected?.provenance?.check)
  const { ref: tabsRef, onWheel: onTabsWheel, onKeyDown: onTabsKey } = useTabStrip(
    shown.map((x) => x.key),
    active?.key ?? null,
    onActivate,
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
  // the tab whose title is being edited
  const [editing, setEditing] = useState<string | null>(null)
  const { busy, error: actionError, run } = useAsync()

  async function remove() {
    if (!selected || !confirm(t('ws.deleteDoc', { title: selected.title || formFor(selected.kind).label }))) return
    const ok = await run(async () => {
      await rag.deleteOutput(selected.id)
      return true
    })
    if (ok) onDeleted(selected.id)
  }

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
        {shown.map(({ tab, key, output: o, source: src }) => {
          const label = o ? o.title || formFor(o.kind).label : (src?.name ?? '')
          if (o && editing === o.id)
            return (
              <InlineRename
                key={key}
                value={label}
                label={t('outputs.renameLabel')}
                maxLength={200}
                onCancel={() => setEditing(null)}
                onCommit={(draft) => {
                  setEditing(null)
                  const next = renamedTitle(draft, o.title)
                  if (next) onRename(o, next)
                }}
              />
            )
          return (
            <span key={key} className={`tab viewer-tab${tab.type === 'source' ? ' source-tab' : ''}${o ? ` status-${o.status}` : ''}${key === active?.key ? ' active' : ''}`}>
              <button
                type="button"
                role="tab"
                data-tab-id={key}
                tabIndex={key === active?.key || (!active && key === shown[0].key) ? 0 : -1}
                aria-selected={key === active?.key}
                className="tab-label"
                onClick={() => onActivate(key)}
                onDoubleClick={() => o?.status === 'ready' && setEditing(o.id)}
                onKeyDown={(e) => {
                  if (e.key === 'F2' && o?.status === 'ready') {
                    e.preventDefault()
                    setEditing(o.id)
                  }
                }}
                title={o ? `${formFor(o.kind).label} · ${formatTime(o.created_at)} · ${t('outputs.renameHint')}` : `${sourceKindLabel(src!.kind)} · ${src!.name}`}
              >
                {src && <span className="tab-kind muted">{sourceKindLabel(src.kind)}</span>}
                {label}
                {o && (o.status === 'processing' || o.status === 'waiting') && <span className="spinner" aria-label={o.status} />}
              </button>
              <button type="button" className="icon tab-close" title={t('viewer.closeTab', { title: label })} aria-label={t('viewer.closeTab', { title: label })} onClick={() => onClose(key)}>
                ×
              </button>
            </span>
          )
        })}
        {shown.length === 0 && <span className="muted">{t('viewer.noDocs')}</span>}
      </div>
      {(error || actionError) && <p className="error no-print">{error ?? actionError}</p>}
      <div className="viewer-body printable" ref={body}>
        {active?.source && <SourceView source={active.source} tab={active.tab} onRead={onSourcesChanged} />}
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
              {judgeHead(selected.provenance) && <span className="muted small check-line judge-line">{judgeHead(selected.provenance)}</span>}
              {selected.status === 'ready' && selected.kind !== 'chart' && selected.provenance && (
                <span className="no-print">
                  <JudgeRequest
                    subject={{ kind: selected.kind, ...(selected.options?.question_count ? { question_count: selected.options.question_count } : {}), ...(selected.options?.card_count ? { card_count: selected.options.card_count } : {}) }}
                    onJudge={(level) => rag.judgeOutput(selected.id, level).then(onChanged)}
                  />
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
            {shareOpen && <ShareCard output={selected} onChanged={(token) => onChanged({ ...selected, share_token: token })} />}
            <OutputProvenance key={selected.id} output={selected} provenance={selected.provenance} presentSources={presentSources} onOpenSource={onOpenSource}>
              <OutputContent
                kind={selected.kind}
                locate={locate ?? null}
                title={selected.title}
                status={selected.status}
                createdAt={selected.created_at}
                phase={selected.phase ?? null}
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
