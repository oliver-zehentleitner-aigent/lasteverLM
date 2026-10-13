import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { rag } from '../api/rag'
import type { AudioContent, Output } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { formatTime } from '../lib/format'
import { formFor } from '../lib/outputs'
import { OutputContent } from './outputs/OutputContent'

interface Props {
  outputs: Output[]
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
}

/** Right column, top: one tab per generated document, newest first, with
 *  the actions per document: ask about this, print, share, full view. */
export function OutputViewer({
  outputs,
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
}: Props) {
  const selected = outputs.find((o) => o.id === selectedId) ?? null
  const enterButton = useRef<HTMLButtonElement>(null)
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
    if (!selected || !confirm(`Delete "${selected.title || formFor(selected.kind).label}"?`)) return
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
            chat
          </button>
          <button
            ref={leaveButton}
            type="button"
            className="icon"
            title="Leave full view (Esc)"
            aria-label="Leave full view"
            onClick={() => onFullView(false)}
          >
            ×
          </button>
        </div>
      )}
      <div className="tabs no-print" role="tablist">
        {outputs.map((o) => (
          <button
            key={o.id}
            type="button"
            role="tab"
            aria-selected={o.id === selectedId}
            className={`tab status-${o.status}${o.id === selectedId ? ' active' : ''}`}
            onClick={() => onSelect(o.id)}
            title={`${formFor(o.kind).label} · ${formatTime(o.created_at)}`}
          >
            {o.title || formFor(o.kind).label}
            {(o.status === 'processing' || o.status === 'waiting') && <span className="spinner" aria-label={o.status} />}
          </button>
        ))}
        {outputs.length === 0 && <span className="muted">Generated documents appear here as tabs.</span>}
      </div>
      {(error || actionError) && <p className="error no-print">{error ?? actionError}</p>}
      <div className="viewer-body printable">
        {selected && (
          <>
            <header className="viewer-head">
              <h1 className="doc-title">{selected.title || formFor(selected.kind).label}</h1>
              <span className="badge">{formFor(selected.kind).label}</span>
              <span className="muted small">{formatTime(selected.created_at)}</span>
              <span className="actions no-print">
                <button type="button" className="link" disabled={selected.status !== 'ready'} onClick={() => onAskAbout(selected)}>
                  ask about this
                </button>
                <button type="button" className="link" disabled={!printable} onClick={() => window.print()}>
                  print
                </button>
                <button type="button" className="link" disabled={selected.status !== 'ready'} onClick={() => setShareOpen((v) => !v)}>
                  {selected.share_token ? 'shared' : 'share'}
                </button>
                {!fullView && (
                  <button ref={enterButton} type="button" className="link" onClick={() => onFullView(true)}>
                    full view
                  </button>
                )}
                <button type="button" className="link danger" disabled={busy} onClick={() => void remove()}>
                  delete
                </button>
              </span>
            </header>
            {shareOpen && (
              <div className="share card no-print">
                {shareUrl ? (
                  <>
                    <p className="small">Anyone with this link can read the document without signing in.</p>
                    <div className="row">
                      <input readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} />
                      <button type="button" className="secondary" onClick={() => void navigator.clipboard?.writeText(shareUrl)}>
                        Copy
                      </button>
                      <button type="button" className="secondary" disabled={busy} onClick={() => void unshare()}>
                        Revoke
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="row">
                    <p className="small">Create a read-only link to this document.</p>
                    <button type="button" disabled={busy} onClick={() => void share()}>
                      Create link
                    </button>
                  </div>
                )}
              </div>
            )}
            <OutputContent
              key={selected.id}
              kind={selected.kind}
              title={selected.title}
              status={selected.status}
              error={selected.error}
              content={selected.content}
              onExpired={() => rag.getOutput(selected.id).then((o) => (o.content as AudioContent).url)}
            />
          </>
        )}
      </div>
    </section>
  )
}
