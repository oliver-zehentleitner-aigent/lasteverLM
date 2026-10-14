import { createContext, useContext } from 'react'

/** Where a citation's source opens in a new browser tab (a PDF on the
 *  cited page), from the notebook's sources; null when it has nothing to
 *  open. Provided by the notebook view, read by the provenance panel for
 *  its small new-tab link next to "open in source". */
export const SourceLinks = createContext<(sourceId: string, page: number | null) => string | null>(() => null)

export const useSourceLink = () => useContext(SourceLinks)
