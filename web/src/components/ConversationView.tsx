import { useEffect, useRef, useState, type FormEvent } from 'react'
import { rag } from '../api/rag'
import type { Citation, Message } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { isRemoved, splitCitations } from '../lib/citations'
import { similarityLabel } from '../lib/provenance'
import { ProvenancePanel } from './ProvenancePanel'
import { t } from '../i18n'
import type { ChatPaneProps } from './ChatPane'

interface ConversationProps extends ChatPaneProps {
  conversationId: string
}

/** One conversation: its history, the question field, and the [n] markers
 *  of each answer as buttons; a click shows the quote under the message and
 *  tells the parent which source to highlight (or which output tab to open,
 *  for a citation into a generated document). */
export function ConversationView({ notebookId, conversationId, scope, presentSources, sources, suggestion, onClearScope, onCitationSelected, onOpenSource }: ConversationProps) {
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

  // every source turned off: nothing to answer from, unless the question is about one document
  const blocked = !scope && sources.total > 0 && sources.selected === 0

  async function ask(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q || blocked) return
    setQuestion('')
    setMessages((prev) => [
      ...prev,
      { id: `local-${Date.now()}`, role: 'user', content: q, citations: null, created_at: new Date().toISOString() },
    ])
    // a question about one document is scoped by it; the selection is for the notebook
    const answer = await run(() => rag.ask(notebookId, conversationId, q, scope?.id, scope ? undefined : sources.sourceIds))
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
                    title={isRemoved(c.source_id, presentSources) ? t('chat.removedTitle', { name: c.source_name }) : c.source_name}
                  >
                    [{c.n}] {c.source_name}
                    {c.page != null && <span className="muted"> {t('chat.page', { page: c.page })}</span>}
                    {similarityLabel(c.similarity) && <span className="muted"> · {similarityLabel(c.similarity)}</span>}
                    {c.source_kind === 'generated' && <span className="muted"> · {t('chat.generated')}</span>}
                    {isRemoved(c.source_id, presentSources) && <span className="muted"> · {t('chat.sourceRemoved')}</span>}
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
                    onOpenSource={onOpenSource}
                  />
                ) : null
              })()}
          </article>
        ))}
        {busy && <p className="muted">…</p>}
        {messages.length === 0 && !busy && <p className="muted">{t('chat.empty')}</p>}
        {messages.length === 0 && !busy && suggestion && (
          <p className="suggestion small">
            {t('chat.tryDemo')}{' '}
            <button
              type="button"
              className="link"
              onClick={() => {
                setQuestion(suggestion)
                input.current?.focus()
              }}
            >
              {suggestion}
            </button>
          </p>
        )}
        <div ref={bottom} />
      </div>
      {error && <p className="error">{error}</p>}
      {scope && (
        <div className="scope">
          <span className="chip">
            {t('chat.about', { title: scope.title || scope.kind })}
            <button type="button" className="icon" title={t('chat.wholeNotebook')} onClick={onClearScope}>
              ×
            </button>
          </span>
        </div>
      )}
      {!scope && sources.selected < sources.total && (
        <p className="muted small source-count">
          {sources.selected === 0 ? t('chat.noSources') : t('chat.sourcesOf', { n: sources.selected, total: sources.total })}
        </p>
      )}
      <form className="ask row" onSubmit={ask}>
        <input
          ref={input}
          placeholder={scope ? t('chat.askAbout', { title: scope.title || scope.kind }) : t('chat.askSources')}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
          autoFocus
        />
        <button type="submit" disabled={busy || blocked || !question.trim()}>
          {t('chat.ask')}
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
