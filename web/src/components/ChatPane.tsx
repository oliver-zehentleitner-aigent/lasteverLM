import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { rag } from '../api/rag'
import type { Citation, Conversation, Message, Output } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { isRemoved, splitCitations } from '../lib/citations'
import { similarityLabel } from '../lib/provenance'
import { ProvenancePanel } from './ProvenancePanel'
import { activeAfterClose } from '../lib/conversations'

interface Props {
  notebookId: string
  /** "ask about this": the document the next questions are scoped to */
  scope: Output | null
  /** sources a citation can still point to; others show as removed */
  presentSources: ReadonlySet<string> | null
  onClearScope: () => void
  onCitationSelected: (c: Citation | null) => void
  /** controls at the right end of the tab bar (the chat height presets) */
  tools?: ReactNode
}

/** A notebook without conversations gets its first one when the chat opens,
 *  so a question always has a conversation to go to. Concurrent calls for
 *  one notebook share the request, so a double mount (React's development
 *  mode) does not create two. */
const firstConversation = new Map<string, Promise<Conversation>>()
function createFirst(notebookId: string): Promise<Conversation> {
  let p = firstConversation.get(notebookId)
  if (!p) {
    p = rag.createConversation(notebookId).finally(() => firstConversation.delete(notebookId))
    firstConversation.set(notebookId, p)
  }
  return p
}

/** Right column, bottom: the chats of one notebook as tabs. "+" opens a new
 *  one, "×" deletes one with its messages after a confirmation; the last
 *  tab closed is replaced by a fresh one, so there is always a chat. */
export function ChatPane({ notebookId, scope, presentSources, onClearScope, onCitationSelected, tools }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => {
      const list = await rag.listConversations(notebookId)
      const shown = list.length > 0 ? list : [await createFirst(notebookId)]
      setConversations(shown)
      setActiveId(shown[shown.length - 1].id)
    })
  }, [notebookId, run])

  function select(id: string) {
    setActiveId(id)
    onCitationSelected(null)
  }

  async function add() {
    const created = await run(() => rag.createConversation(notebookId))
    if (created) {
      setConversations((prev) => [...prev, created])
      select(created.id)
    }
  }

  async function close(c: Conversation) {
    if (!confirm('Close this chat? Its messages are deleted.')) return
    const next = await run(async () => {
      await rag.deleteConversation(c.id)
      const nextId = activeAfterClose(
        conversations.map((x) => x.id),
        c.id,
        activeId,
      )
      const rest = conversations.filter((x) => x.id !== c.id)
      if (nextId) return { list: rest, active: nextId }
      const fresh = await rag.createConversation(notebookId)
      return { list: [fresh], active: fresh.id }
    })
    if (next) {
      setConversations(next.list)
      if (next.active !== activeId) select(next.active)
    }
  }

  const active = conversations.find((c) => c.id === activeId) ?? null

  return (
    <section className="pane chat">
      <div className="tabs chat-tabs" role="tablist" aria-label="Chats">
        {conversations.map((c) => (
          <span key={c.id} className={c.id === activeId ? 'tab active' : 'tab'}>
            <button type="button" role="tab" className="tab-label" aria-selected={c.id === activeId} onClick={() => select(c.id)}>
              {c.title}
            </button>
            <button type="button" className="icon" title="Close this chat" disabled={busy} onClick={() => void close(c)}>
              ×
            </button>
          </span>
        ))}
        <button type="button" className="icon" title="New chat" disabled={busy} onClick={() => void add()}>
          +
        </button>
        {tools && <span className="tab-tools">{tools}</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {active && (
        <ConversationView
          key={active.id}
          notebookId={notebookId}
          conversationId={active.id}
          scope={scope}
          presentSources={presentSources}
          onClearScope={onClearScope}
          onCitationSelected={onCitationSelected}
        />
      )}
    </section>
  )
}

interface ConversationProps extends Props {
  conversationId: string
}

/** One conversation: its history, the question field, and the [n] markers
 *  of each answer as buttons; a click shows the quote under the message and
 *  tells the parent which source to highlight (or which output tab to open,
 *  for a citation into a generated document). */
function ConversationView({ notebookId, conversationId, scope, presentSources, onClearScope, onCitationSelected }: ConversationProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [open, setOpen] = useState<{ messageId: string; n: number } | null>(null)
  const { busy, error, run } = useAsync()
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void run(async () => setMessages(await rag.listMessages(conversationId)))
  }, [conversationId, run])

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, busy])

  useEffect(() => {
    if (scope) input.current?.focus()
  }, [scope])

  async function ask(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q) return
    setQuestion('')
    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: 'user', content: q, citations: null, created_at: new Date().toISOString() },
    ])
    const answer = await run(() => rag.ask(notebookId, conversationId, q, scope?.id))
    if (answer) {
      setMessages((prev) => [
        ...prev,
        {
          id: answer.message_id,
          role: 'assistant',
          content: answer.answer,
          citations: answer.citations,
          created_at: new Date().toISOString(),
        },
      ])
    }
  }

  function toggle(m: Message, c: Citation) {
    const same = open?.messageId === m.id && open.n === c.n
    setOpen(same ? null : { messageId: m.id, n: c.n })
    onCitationSelected(same ? null : c)
  }

  return (
    <>
      <div className="messages">
        {messages.map((m) => (
          <article key={m.id} className={`msg ${m.role}`}>
            <AnswerText message={m} onCite={(c) => toggle(m, c)} openN={open?.messageId === m.id ? open.n : null} />
            {m.role === 'assistant' && m.citations && m.citations.length > 0 && (
              <footer className="cites">
                {m.citations.map((c) => (
                  <button
                    key={c.n}
                    type="button"
                    className={[open?.messageId === m.id && open.n === c.n ? 'cite open' : 'cite', isRemoved(c.source_id, presentSources) ? 'removed' : '']
                      .join(' ')
                      .trim()}
                    onClick={() => toggle(m, c)}
                    title={isRemoved(c.source_id, presentSources) ? `${c.source_name} (removed from this notebook)` : c.source_name}
                  >
                    [{c.n}] {c.source_name}
                    {c.page != null && <span className="muted"> p. {c.page}</span>}
                    {similarityLabel(c.similarity) && <span className="muted"> · {similarityLabel(c.similarity)}</span>}
                    {c.source_kind === 'generated' && <span className="muted"> · generated</span>}
                    {isRemoved(c.source_id, presentSources) && <span className="muted"> · source removed</span>}
                  </button>
                ))}
              </footer>
            )}
            {open?.messageId === m.id &&
              (() => {
                const c = m.citations?.find((x) => x.n === open.n)
                return c ? (
                  <ProvenancePanel
                    key={c.n}
                    citation={c}
                    answer={m.content}
                    removed={isRemoved(c.source_id, presentSources)}
                    onOpenSource={onCitationSelected}
                  />
                ) : null
              })()}
          </article>
        ))}
        {busy && <p className="muted">…</p>}
        {messages.length === 0 && !busy && <p className="muted">Ask a question about the sources of this notebook.</p>}
        <div ref={bottom} />
      </div>
      {error && <p className="error">{error}</p>}
      {scope && (
        <div className="scope">
          <span className="chip">
            about: {scope.title || scope.kind}
            <button type="button" className="icon" title="Ask the whole notebook again" onClick={onClearScope}>
              ×
            </button>
          </span>
        </div>
      )}
      <form className="ask row" onSubmit={ask}>
        <input
          ref={input}
          placeholder={scope ? `Ask about "${scope.title || scope.kind}"…` : 'Ask your sources…'}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
          autoFocus
        />
        <button type="submit" disabled={busy || !question.trim()}>
          Ask
        </button>
      </form>
    </>
  )
}

function AnswerText({ message, onCite, openN }: { message: Message; onCite: (c: Citation) => void; openN: number | null }) {
  if (message.role !== 'assistant' || !message.citations || message.citations.length === 0) {
    return <p>{message.content}</p>
  }
  const byN = new Map(message.citations.map((c) => [c.n, c]))
  const parts = splitCitations(message.content, new Set(byN.keys()))
  return (
    <p>
      {parts.map((p, i) =>
        p.kind === 'text' ? (
          <span key={i}>{p.text}</span>
        ) : (
          <button key={i} type="button" className={openN === p.n ? 'marker open' : 'marker'} onClick={() => onCite(byN.get(p.n)!)}>
            [{p.n}]
          </button>
        ),
      )}
    </p>
  )
}
