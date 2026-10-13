/** Splits an answer into text and citation markers. The contract writes
 *  markers inline as [1], [2]; the model also produces grouped markers
 *  such as [1, 2, 5], which are split into one marker per number. Markers
 *  with no matching citation are kept as plain text rather than dropped,
 *  so a mismatch between answer and citations stays visible. */

export type AnswerPart = { kind: 'text'; text: string } | { kind: 'cite'; n: number }

const MARKER = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g

export function splitCitations(answer: string, known: ReadonlySet<number>): AnswerPart[] {
  const parts: AnswerPart[] = []
  let last = 0
  for (const m of answer.matchAll(MARKER)) {
    const numbers = m[1].split(',').map((s) => Number(s.trim()))
    const start = m.index ?? 0
    const cites = numbers.filter((n) => known.has(n))
    if (cites.length === 0) continue
    if (start > last) parts.push({ kind: 'text', text: answer.slice(last, start) })
    if (cites.length < numbers.length) {
      // keep the unknown numbers visible as text, cite the known ones
      parts.push({ kind: 'text', text: `[${numbers.filter((n) => !known.has(n)).join(', ')}]` })
    }
    for (const n of cites) parts.push({ kind: 'cite', n })
    last = start + m[0].length
  }
  if (last < answer.length) parts.push({ kind: 'text', text: answer.slice(last) })
  return parts
}

/** A citation whose source is no longer in the notebook: detached from it,
 *  deleted from the library, or a generated document that was deleted.
 *  `present` is null while the notebook's lists are still loading, and
 *  then nothing counts as removed. */
export function isRemoved(sourceId: string, present: ReadonlySet<string> | null): boolean {
  return present !== null && !present.has(sourceId)
}
