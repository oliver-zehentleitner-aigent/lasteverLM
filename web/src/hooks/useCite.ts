import { createContext, useContext } from 'react'
import type { JudgeNote } from '../api/types'

/** A document's passage markers, from OutputProvenance to its renderer. */
export interface Cite {
  /** the passage numbers that exist */
  known: ReadonlySet<number>
  open: number | null
  /** `judge`: the claim's judge note, shown in the panel with the passage */
  cite: (n: number, claim: string, judge?: JudgeNote) => void
  /** "Have it judged" after a claim the word check could not measure: the
   *  label with the judging's price, and what opens Check with a judge;
   *  absent where nothing can be judged (the share page) */
  judgeAsk?: { label: string; open: () => void }
}

export const CiteContext = createContext<Cite | null>(null)

/** For the renderers: null when the document has no provenance, then they
 *  draw no markers. */
export function useCite(): Cite | null {
  return useContext(CiteContext)
}
