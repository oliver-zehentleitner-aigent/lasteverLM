import type { QuizQuestion } from '../api/types'

/** The contract allows the answer as option text or as index; both
 *  resolve to an index, -1 when the answer matches no option. */
export function answerIndex(q: QuizQuestion): number {
  if (typeof q.answer === 'number') return q.answer >= 0 && q.answer < q.options.length ? q.answer : -1
  const exact = q.options.indexOf(q.answer)
  if (exact >= 0) return exact
  const norm = (s: string) => s.trim().toLowerCase()
  return q.options.findIndex((o) => norm(o) === norm(q.answer as string))
}

export function score(questions: QuizQuestion[], chosen: (number | null)[]): { correct: number; answered: number } {
  let correct = 0
  let answered = 0
  questions.forEach((q, i) => {
    const c = chosen[i]
    if (c === null || c === undefined) return
    answered += 1
    if (c === answerIndex(q)) correct += 1
  })
  return { correct, answered }
}
