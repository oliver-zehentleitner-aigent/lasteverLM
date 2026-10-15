import { createContext, useContext } from 'react'
import type { Source } from '../api/types'

/** Where a citation's source opens in a new browser tab (a PDF on the
 *  cited page), from the notebook's sources; null when it has nothing to
 *  open. Provided by the notebook view, read by the provenance panel for
 *  its small new-tab link next to "open in source". */
export const SourceLinks = createContext<(sourceId: string, page: number | null) => string | null>(() => null)

export const useSourceLink = () => useContext(SourceLinks)

/** A citation's source as the notebook lists it (its kind, capture and
 *  `read_by`); undefined outside a notebook (the share page) or for a
 *  generated document. */
export const SourceInfo = createContext<(sourceId: string) => Source | undefined>(() => undefined)

export const useSourceInfo = () => useContext(SourceInfo)
