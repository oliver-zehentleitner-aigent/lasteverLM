import { Fragment, useEffect, useRef, useState, type FormEvent } from 'react'
import { rag } from '../api/rag'
import type { AnswerUnit, Citation, Message } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useEstimate } from '../hooks/useEstimate'
import { isRemoved, splitCitations } from '../lib/citations'
import { isStacked } from '../lib/layout'
import { similarityLabel } from '../lib/provenance'
import { checkSummary, unitBadges } from '../lib/outputProvenance'
import { judgeBadge } from '../lib/judge'
import { JudgeRequest } from './JudgeRequest'
import { AnswerActions, SuggestionCards } from './AnswerActions'
import { StarterQuestions } from './StarterQuestions'
import { PriceTag } from './PriceTag'
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
export function ConversationView({ notebookId, conversationId, scope, presentSources, sources, onClearScope, onCitationSelected, onOpenSource }: ConversationProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [open, setOpen] = useState<{ messageId: string; n: number } | null>(null)
  const { busy, error, run } = useAsync()
  const price = useEstimate({ action: 'chat_answer' })
  const pane = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void run(async () => setMessages(await rag.listMessages(conversationId)))
  }, [conversationId, run])

  // the newest message in view: the messages pane scrolls, never the page
  // (scrollIntoView would scroll every ancestor, the document included)
  useEffect(() => {
    const el = pane.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length, busy])

  // the question field takes the focus where the chat is on screen beside
  // the documents; stacked, it is below the fold and the page stays put
  useEffect(() => {
    if (!isStacked()) input.current?.focus({ preventScroll: true })
  }, [conversationId])

  // "ask about this" was just clicked: the field is where the answer goes
  useEffect(() => {
    if (scope) input.current?.focus({ preventScroll: true })
  }, [scope])

  // every source turned off: nothing to answer from, unless the question is about one document
  const blocked = !scope && sources.total > 0 && sources.selected === 0

  function ask(e: FormEvent) {
    e.preventDefault()
    void send(question.trim())
  }

  /** Asks `q`: from the field, or a suggestion card. */
  async function send(q: string) {
    if (!q || blocked || busy) return
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
          units: answer.units ?? null,
          check: answer.check ?? null,
          suggestions: answer.suggestions ?? [],
          feedback: null,
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
      <div className="messages" ref={pane}>
        {messages.map((m, i) => (
          <article key={m.id} id={`msg-${m.id}`} className={`msg ${m.role}`}>
            <AnswerText message={m} onCite={(c) => toggle(m, c)} openN={open?.messageId === m.id ? open.n : null} />
            {m.role === 'assistant' && checkSummary(m.check) && (
              <p
                className="muted small check-line"
                title={m.check?.method ? t('outProv.checkTitle', { method: m.check.method, threshold: m.check.threshold ?? '' }) : undefined}
              >
                {checkSummary(m.check)}
              </p>
            )}
            {m.role === 'assistant' && m.citations && m.citations.length > 0 && !m.id.startsWith('local-') && (
              <p className="small no-print">
                <JudgeRequest
                  compact
                  onJudge={(level) =>
                    rag.judgeMessage(m.id, level).then((judged) => setMessages((prev) => prev.map((x) => (x.id === m.id ? { ...x, units: judged.units, check: judged.check ?? x.check } : x))))
                  }
                />
              </p>
            )}
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
            {m.role === 'assistant' && !m.id.startsWith('local-') && (
              <AnswerActions message={m} target={byId(`msg-${m.id}`)} onRated={(rated) => setMessages((prev) => prev.map((x) => (x.id === rated.id ? rated : x)))} />
            )}
            {m.role === 'assistant' && i === messages.length - 1 && !busy && <SuggestionCards suggestions={m.suggestions ?? []} disabled={busy || blocked} onAsk={(q) => void send(q)} />}
          </article>
        ))}
        {busy && <p className="muted">…</p>}
        {messages.length === 0 && !busy && <p className="muted">{t('chat.empty')}</p>}
        {messages.length === 0 && !busy && <StarterQuestions notebookId={notebookId} disabled={blocked} onAsk={(q) => void send(q)} />}
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
        />
        <button type="submit" disabled={busy || blocked || !question.trim()}>
          {t('chat.ask')}
        </button>
      </form>
      <p className="ask-price no-print">
        <PriceTag state={price} suffix={t('price.perQuestion')} />
      </p>
    </>
  )
}

/** The element with this id, looked up when it is needed (a copy that
 *  falls back to selecting the answer). */
const byId = (id: string) => ({
  get current() {
    return document.getElementById(id)
  },
})

/** An answer with its [n] markers as buttons and, after each citing
 *  paragraph the check did not back, its badge (the paragraph stays). */
function AnswerText({ message, onCite, openN }: { message: Message; onCite: (c: Citation) => void; openN: number | null }) {
  if (message.role !== 'assistant' || !message.citations || message.citations.length === 0) {
    return <p>{message.content}</p>
  }
  const byN = new Map(message.citations.map((c) => [c.n, c]))
  const known = new Set(byN.keys())
  // the answer cut after each badged paragraph, each piece with its markers
  const badges = unitBadges(message.content, message.units)
  const pieces: { text: string; badge: (typeof badges)[number]['badge']; unit: AnswerUnit | null }[] = []
  let at = 0
  for (const b of badges) {
    pieces.push({ text: message.content.slice(at, b.end), badge: b.badge, unit: b.unit })
    at = b.end
  }
  pieces.push({ text: message.content.slice(at), badge: null, unit: null })
  return (
    <p>
      {pieces.map((piece, k) => (
        <Fragment key={k}>
          {splitCitations(piece.text, known).map((p, i) =>
            p.kind === 'text' ? (
              <span key={i}>{p.text}</span>
            ) : (
              <button key={i} type="button" className={openN === p.n ? 'marker open' : 'marker'} onClick={() => onCite(byN.get(p.n)!)}>
                [{p.n}]
              </button>
            ),
          )}
          {piece.badge && (
            <span className={`badge support-${piece.badge}`} title={t(`outProv.${piece.badge}Title`)}>
              {t(`outProv.${piece.badge}`)}
            </span>
          )}
          {piece.unit && <ChatJudgeBadge unit={piece.unit} />}
        </Fragment>
      ))}
    </p>
  )
}

/** A judged paragraph's verdict; the reason and the decisive passage as
 *  its tooltip (the chat's panel is per citation, not per paragraph). */
function ChatJudgeBadge({ unit }: { unit: AnswerUnit }) {
  const b = judgeBadge(unit)
  if (!b || !unit.judge) return null
  const title = unit.judge.quote ? `${b.title}\n${t('judge.quote')}: “${unit.judge.quote}”` : b.title
  return (
    <span className={`badge judge judge-${b.verdict}${b.disagree ? ' disagree' : ''}`} title={title}>
      {t('judge.section')}: {b.label}
    </span>
  )
}
