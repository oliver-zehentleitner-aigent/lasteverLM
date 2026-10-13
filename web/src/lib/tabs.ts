/** The tab a key moves to in a tab bar: arrows step (wrapping), Home and
 *  End jump; null for any other key or an empty bar. */
export function tabForKey(ids: readonly string[], current: string | null, key: string): string | null {
  if (ids.length === 0) return null
  const at = current === null ? -1 : ids.indexOf(current)
  switch (key) {
    case 'ArrowRight':
      return ids[(at + 1 + ids.length) % ids.length]
    case 'ArrowLeft':
      return ids[(at - 1 + ids.length) % ids.length]
    case 'Home':
      return ids[0]
    case 'End':
      return ids[ids.length - 1]
    default:
      return null
  }
}
