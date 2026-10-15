/** What the workspace opens once the notebook list is in. The notebook
 *  that was open stays; else the first one (for a new user that is the
 *  starter notebook, which ingest copies into the first list). Without
 *  any notebook and with the introduction still to show, a first notebook
 *  is made, so the tour has the view its arrows point at; otherwise the
 *  empty state stays. Pure, so it is tested. */
export function firstSelection(ids: readonly string[], current: string | null, tourPending: boolean): { select: string | null; createFirst: boolean } {
  if (current && ids.includes(current)) return { select: current, createFirst: false }
  if (ids.length > 0) return { select: ids[0], createFirst: false }
  return { select: null, createFirst: tourPending }
}
