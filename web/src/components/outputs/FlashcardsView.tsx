import { useState, type KeyboardEvent } from 'react'
import type { FlashcardsContent } from '../../api/types'
import { t } from '../../i18n'
import { progress, shuffled, toAnkiCsv, type CardMark } from '../../lib/flashcards'
import { ClaimMarks } from '../OutputProvenance'

/** Flashcards: one card at a time; a click or Space turns it, the arrows
 *  move, Shuffle mixes the order; on the back "Knew it" or "Again" marks
 *  it for this session with a progress line. A list view shows every card.
 *  The back carries the passages' [n] markers and the check's badges, as
 *  the quiz does. CSV for Anki (front;back). Nothing is saved. */
export function FlashcardsView({ content, title }: { content: FlashcardsContent; title: string }) {
  const cards = content.cards ?? []
  const [order, setOrder] = useState<number[]>(() => cards.map((_, i) => i))
  const [pos, setPos] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [hint, setHint] = useState(false)
  const [marks, setMarks] = useState<Map<number, CardMark>>(new Map())
  const [list, setList] = useState(false)

  if (cards.length === 0) return <p className="muted">{t('content.none')}</p>
  const index = order[pos] ?? 0
  const card = cards[index]
  const p = progress(cards.length, marks)

  function go(next: number) {
    setPos((next + cards.length) % cards.length)
    setFlipped(false)
    setHint(false)
  }
  function mark(m: CardMark) {
    setMarks((prev) => new Map(prev).set(index, m))
    if (pos < cards.length - 1) go(pos + 1)
  }
  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.target instanceof HTMLInputElement) return
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault()
      setFlipped((f) => !f)
    } else if (e.key === 'ArrowRight') go(pos + 1)
    else if (e.key === 'ArrowLeft') go(pos - 1)
  }
  function download() {
    const blob = new Blob([toAnkiCsv(cards)], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${(title || 'flashcards').replace(/[^\w.-]+/g, '_')}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="flashcards">
      <div className="flash-bar no-print">
        <span className="presets flash-mode" role="radiogroup" aria-label={t('flash.view')}>
          <button type="button" role="radio" aria-checked={!list} className={list ? 'preset' : 'preset active'} onClick={() => setList(false)}>
            {t('flash.oneAtATime')}
          </button>
          <button type="button" role="radio" aria-checked={list} className={list ? 'preset active' : 'preset'} onClick={() => setList(true)}>
            {t('flash.list')}
          </button>
        </span>
        {!list && (
          <button
            type="button"
            className="secondary small"
            onClick={() => {
              setOrder(shuffled(cards.length))
              go(0)
            }}
          >
            {t('flash.shuffle')}
          </button>
        )}
        <button type="button" className="secondary small" onClick={download}>
          {t('flash.csv')}
        </button>
        <span className="muted small">{t('flash.progress', { knew: p.knew, again: p.again, open: p.open })}</span>
      </div>
      {list ? (
        <ol className="flash-list">
          {cards.map((c, i) => (
            <li key={i} className={marks.get(i) ? `marked-${marks.get(i)}` : undefined}>
              <p className="flash-front">{c.front}</p>
              <p className="flash-back">
                {c.back} <ClaimMarks claim={c} text={`${c.front} ${c.back}`} />
              </p>
            </li>
          ))}
        </ol>
      ) : (
        <div className="flash-stage" tabIndex={0} onKeyDown={onKey} aria-label={t('flash.keys')}>
          <p className="muted small">{t('flash.position', { n: pos + 1, total: cards.length })}</p>
          <button type="button" className={flipped ? 'flash-card back' : 'flash-card'} aria-pressed={flipped} onClick={() => setFlipped((f) => !f)}>
            <span className="flash-side muted small">{flipped ? t('flash.back') : t('flash.front')}</span>
            <span className="flash-text">{flipped ? card.back : card.front}</span>
          </button>
          {flipped ? (
            <div className="flash-after">
              <ClaimMarks claim={card} text={`${card.front} ${card.back}`} />
              <button type="button" className="secondary small" onClick={() => mark('knew')}>
                {t('flash.knew')}
              </button>
              <button type="button" className="secondary small" onClick={() => mark('again')}>
                {t('flash.again')}
              </button>
              {marks.get(index) && <span className="muted small">{t(`flash.marked.${marks.get(index)!}`)}</span>}
            </div>
          ) : (
            card.hint && (
              <p className="small">
                {hint ? (
                  <span className="muted">{card.hint}</span>
                ) : (
                  <button type="button" className="link" onClick={() => setHint(true)}>
                    {t('flash.hint')}
                  </button>
                )}
              </p>
            )
          )}
          <div className="flash-nav no-print">
            <button type="button" className="secondary small" onClick={() => go(pos - 1)} aria-label={t('flash.prev')}>
              ←
            </button>
            <button type="button" className="secondary small" onClick={() => go(pos + 1)} aria-label={t('flash.next')}>
              →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
