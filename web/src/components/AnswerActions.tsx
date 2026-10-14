import { useState, type FormEvent, type RefObject } from 'react'
import { rag } from '../api/rag'
import type { Message } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { t } from '../i18n'
import { answerForClipboard } from '../lib/answerCopy'
import { CopyButton } from './CopyButton'

const COMMENT_MAX = 1000

/** The row under an answer: copy (the text with its [n] markers and the
 *  cited passages), thumbs up, thumbs down. The rating shows as pressed
 *  and can be changed; down asks for an optional one-line comment. */
export function AnswerActions({ message, target, onRated }: { message: Message; target: RefObject<HTMLElement | null>; onRated: (m: Message) => void }) {
  const rating = message.feedback?.rating ?? null
  const [asking, setAsking] = useState(false)
  const [comment, setComment] = useState('')
  const { busy, error, run } = useAsync()

  async function rate(r: 'up' | 'down', note?: string) {
    const rated = await run(() => rag.rateMessage(message.id, r, note))
    if (rated) {
      onRated({ ...message, feedback: rated.feedback ?? { rating: r, comment: note ?? null, at: new Date().toISOString() } })
      setAsking(false)
      setComment('')
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    void rate('down', comment.trim() || undefined)
  }

  return (
    <div className="answer-actions no-print">
      <CopyButton text={answerForClipboard(message.content, message.citations)} target={target} label={t('chat.copy')} />
      <button type="button" className={rating === 'up' ? 'icon rate active' : 'icon rate'} aria-pressed={rating === 'up'} title={t('chat.rateUp')} aria-label={t('chat.rateUp')} disabled={busy} onClick={() => void rate('up')}>
        👍
      </button>
      <button
        type="button"
        className={rating === 'down' ? 'icon rate active' : 'icon rate'}
        aria-pressed={rating === 'down'}
        aria-expanded={asking}
        title={t('chat.rateDown')}
        aria-label={t('chat.rateDown')}
        disabled={busy}
        onClick={() => setAsking((v) => !v)}
      >
        👎
      </button>
      {rating === 'down' && message.feedback?.comment && !asking && <span className="muted small rate-comment">{message.feedback.comment}</span>}
      {asking && (
        <form className="rate-form" onSubmit={submit}>
          <input
            autoFocus
            maxLength={COMMENT_MAX}
            placeholder={t('chat.rateComment')}
            aria-label={t('chat.rateComment')}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setAsking(false)}
          />
          <button type="submit" className="secondary small" disabled={busy}>
            {t('chat.rateSend')}
          </button>
        </form>
      )}
      {error && <span className="error small">{error}</span>}
    </div>
  )
}

/** Up to three questions as cards; a click asks it. */
export function SuggestionCards({ suggestions, disabled, onAsk }: { suggestions: readonly string[]; disabled: boolean; onAsk: (q: string) => void }) {
  if (suggestions.length === 0) return null
  return (
    <div className="suggestion-cards no-print" role="group" aria-label={t('chat.suggestions')}>
      {suggestions.slice(0, 3).map((q) => (
        <button key={q} type="button" className="suggestion-card" disabled={disabled} onClick={() => onAsk(q)}>
          {q}
        </button>
      ))}
    </div>
  )
}
