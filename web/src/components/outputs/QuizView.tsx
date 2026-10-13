import { useState } from 'react'
import type { QuizContent } from '../../api/types'
import { answerIndex, score } from '../../lib/quiz'
import { t } from '../../i18n'

/** Interactive quiz: pick an option, the right one and the explanation are
 *  revealed per question; a running score sits at the top. */
export function QuizView({ content }: { content: QuizContent }) {
  const questions = content.questions ?? []
  const [chosen, setChosen] = useState<(number | null)[]>(() => questions.map(() => null))
  const s = score(questions, chosen)

  return (
    <div className="quiz">
      <p className="muted">
        {t('quiz.progress', { answered: s.answered, total: questions.length, correct: s.correct })}
        {s.answered > 0 && (
          <>
            {' '}
            <button type="button" className="link" onClick={() => setChosen(questions.map(() => null))}>
              {t('quiz.restart')}
            </button>
          </>
        )}
      </p>
      <ol>
        {questions.map((q, i) => {
          const picked = chosen[i]
          const right = answerIndex(q)
          return (
            <li key={i} className="question">
              <p className="q">{q.question}</p>
              <ul className="options">
                {q.options.map((o, j) => {
                  const cls =
                    picked === null ? 'option' : j === right ? 'option right' : j === picked ? 'option wrong' : 'option muted'
                  return (
                    <li key={j}>
                      <button
                        type="button"
                        className={cls}
                        disabled={picked !== null}
                        onClick={() => setChosen((c) => c.map((v, k) => (k === i ? j : v)))}
                      >
                        {o}
                      </button>
                    </li>
                  )
                })}
              </ul>
              {picked !== null && (
                <p className="explanation">
                  {right === -1 && <span className="error">{t('quiz.noKey')} </span>}
                  {q.explanation}
                </p>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
