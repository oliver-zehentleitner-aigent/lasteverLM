/** Formatting and the passage heuristic for the citation provenance panel. */

/** "chunk 12 of 43"; the index is 0-based. Null when unknown. */
export function chunkPosition(index: number | null | undefined, count: number | null | undefined): string | null {
  if (index === null || index === undefined || count === null || count === undefined) return null
  return `chunk ${index + 1} of ${count}`
}

/** Similarity as shown next to a citation, two decimals; null when unknown. */
export function similarityLabel(s: number | null | undefined): string | null {
  return s === null || s === undefined || !Number.isFinite(s) ? null : s.toFixed(2)
}

/** The bar's width in percent, clamped to 0–100. */
export function similarityPercent(s: number): number {
  return Math.round(Math.min(1, Math.max(0, s)) * 100)
}

const MARKERS = /\[\d{1,3}(?:\s*,\s*\d{1,3})*\]/g

/** The sentence of the answer that carries marker n, without markers: the
 *  claim the citation is meant to back. Empty when n is not cited. */
export function claimFor(answer: string, n: number): string {
  const sentences = answer.match(/[^.!?]+[.!?]*/g) ?? [answer]
  const hit = sentences.find((s) =>
    [...s.matchAll(MARKERS)].some((m) => m[0].slice(1, -1).split(',').some((x) => Number(x.trim()) === n)),
  )
  return (hit ?? '').replace(MARKERS, '').replace(/\s+([.!?,;:])/g, '$1').trim()
}

const words = (s: string) => new Set(s.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) ?? [])

/** Splits the chunk around its sentence that shares the most words with the
 *  claim, so that sentence can be highlighted. The backend sends no span,
 *  so this is a best guess; with no overlap nothing is highlighted. */
export function highlightPassage(chunk: string, claim: string): { before: string; match: string; after: string } {
  const target = words(claim)
  let best: { start: number; end: number; score: number } | null = null
  for (const m of chunk.matchAll(/[^.!?\n]+[.!?]*/g)) {
    const own = words(m[0])
    let score = 0
    for (const w of own) if (target.has(w)) score += 1
    if (score > 0 && (!best || score > best.score)) best = { start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, score }
  }
  if (!best) return { before: chunk, match: '', after: '' }
  return { before: chunk.slice(0, best.start), match: chunk.slice(best.start, best.end), after: chunk.slice(best.end) }
}
