/** What a key does on a focused mind map: fit with 0, zoom with + / =
 *  and − / -; null for anything else (so the page keeps its keys). */
export function mapAction(key: string): { kind: 'fit' } | { kind: 'zoom'; by: number } | null {
  if (key === '0') return { kind: 'fit' }
  if (key === '+' || key === '=') return { kind: 'zoom', by: 1.25 }
  if (key === '-' || key === '−' || key === '_') return { kind: 'zoom', by: 0.8 }
  return null
}
