import { words } from './words'

/* Finding a cited passage inside a generated document that the viewer
   shows: the chunk is the document's own text (a report's paragraphs, a
   mind map's outline), so the best block is the one sharing the most
   words with it. */

/** The index of the candidate text that matches the chunk best, or -1 when
 *  none shares at least two words (or all of its own, for short labels). */
export function bestMatchIndex(candidates: readonly string[], chunk: string): number {
  const target = words(chunk)
  let best = -1
  let bestScore = 0
  candidates.forEach((text, i) => {
    const own = words(text)
    if (own.size === 0) return
    let score = 0
    for (const w of own) if (target.has(w)) score += 1
    const enough = score >= 2 || (score === own.size && score > 0)
    // prefer more shared words, then the shorter (more specific) block
    if (enough && (score > bestScore || (score === bestScore && best >= 0 && text.length < candidates[best].length))) {
      best = i
      bestScore = score
    }
  })
  return best
}

/** A mind map chunk's first line without Markdown list or heading marks:
 *  the label of the node it starts at. */
export function firstLine(chunk: string): string {
  const line = chunk.split('\n').find((l) => l.trim()) ?? ''
  return line.replace(/^\s*(?:[-*+]|#+|\d+\.)\s+/, '').trim()
}

/** A request to show a cited passage: which document, the chunk text, and
 *  a nonce so the same citation opened twice runs the search again. */
export interface LocateRequest {
  outputId: string
  text: string
  nonce: number
}

/** Scrolls an element to the middle of its scroll area and lets it flash. */
export function flash(el: Element): void {
  el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  el.classList.remove('flash')
  // restart the animation when the same block is located twice
  void (el as HTMLElement).offsetWidth
  el.classList.add('flash')
  window.setTimeout(() => el.classList.remove('flash'), 1800)
}
