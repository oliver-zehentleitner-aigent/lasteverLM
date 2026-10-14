import { createContext, useContext } from 'react'

/** A document's passage markers, from OutputProvenance to its renderer. */
export interface Cite {
  /** the passage numbers that exist */
  known: ReadonlySet<number>
  open: number | null
  cite: (n: number, claim: string) => void
}

export const CiteContext = createContext<Cite | null>(null)

/** For the renderers: null when the document has no provenance, then they
 *  draw no markers. */
export function useCite(): Cite | null {
  return useContext(CiteContext)
}
