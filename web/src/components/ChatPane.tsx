import { useEffect, useRef, useState, type FormEvent } from 'react'
import { rag } from '../api/rag'
import type { Citation, Message, Output } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { splitCitations } from '../lib/citations'

interface Props {
  notebookId: string
  /** "ask about this": the document the next questions are scoped to */
  scope: Output | null
  onClearScope: () => void
  onCitationSelected: (c: Citation | null) => void
}

/** Right column, bottom: the conversation of one notebook. Each assistant
 *  message renders its [n] markers as buttons; a click shows the quote
 *  under the message and tells the parent which source to highlight (or
 *  which output tab to open, for a citation into a generated document). */
export function ChatPane({ notebookId, scope, onClearScope, onCitationSelected }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [open, setOpen] = useState<{ messageId: string; n: number } | null>(null)
  const { busy, error, run } = useAsync()
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void run(async () => setMessages(await rag.listMessages(notebookId)))
  }, [notebookId, run])

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
    const answer = await run(() => rag.ask(notebookId, q, scope?.id))
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
    <section className="pane chat">
      <h2>Chat</h2>
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
                    className={open?.messageId === m.id && open.n === c.n ? 'cite open' : 'cite'}
                    onClick={() => toggle(m, c)}
                    title={c.source_name}
                  >
                    [{c.n}] {c.source_name}
                    {c.page != null && <span className="muted"> p. {c.page}</span>}
                    {c.source_kind === 'generated' && <span className="muted"> · generated</span>}
                  </button>
                ))}
              </footer>
            )}
            {open?.messageId === m.id && m.citations && <Quote citation={m.citations.find((c) => c.n === open.n)} />}
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
    </section>
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

function Quote({ citation }: { citation: Citation | undefined }) {
  if (!citation) return null
  return (
    <blockquote className="quote">
      <cite>
        {citation.source_name}
        {citation.page != null && `, p. ${citation.page}`}
      </cite>
      {citation.quote}
    </blockquote>
  )
}
