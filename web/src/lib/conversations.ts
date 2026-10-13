/** The tab to show after one closes: the active one stays if another tab
 *  closed; closing the active tab moves to its right neighbour, or to the
 *  left one at the end of the bar. Null when no tab is left. */
export function activeAfterClose(ids: readonly string[], closed: string, active: string | null): string | null {
  const rest = ids.filter((id) => id !== closed)
  if (rest.length === 0) return null
  if (active !== closed && active !== null && rest.includes(active)) return active
  const at = ids.indexOf(closed)
  return rest[Math.min(Math.max(at, 0), rest.length - 1)]
}
