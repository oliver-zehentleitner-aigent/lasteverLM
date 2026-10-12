/** Splits an answer into text and citation markers. The contract writes
 *  markers inline as [1], [2]; `n` maps a marker to one citation. Markers
 *  with no matching citation are kept as plain text rather than dropped,
 *  so a mismatch between answer and citations stays visible. */

export type AnswerPart = { kind: 'text'; text: string } | { kind: 'cite'; n: number }

const MARKER = /\[(\d{1,3})\]/g

export function splitCitations(answer: string, known: ReadonlySet<number>): AnswerPart[] {
  const parts: AnswerPart[] = []
  let last = 0
  for (const m of answer.matchAll(MARKER)) {
    const n = Number(m[1])
    const start = m.index ?? 0
    if (!known.has(n)) continue
    if (start > last) parts.push({ kind: 'text', text: answer.slice(last, start) })
    parts.push({ kind: 'cite', n })
    last = start + m[0].length
  }
  if (last < answer.length) parts.push({ kind: 'text', text: answer.slice(last) })
  return parts
}
