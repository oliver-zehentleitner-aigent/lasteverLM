/** What a key does on a focused mind map: fit with 0, zoom with + / =
 *  and − / -; null for anything else (so the page keeps its keys). */
export function mapAction(key: string): { kind: 'fit' } | { kind: 'zoom'; by: number } | null {
  if (key === '0') return { kind: 'fit' }
  if (key === '+' || key === '=') return { kind: 'zoom', by: 1.25 }
  if (key === '-' || key === '−' || key === '_') return { kind: 'zoom', by: 0.8 }
  return null
}

/** What the wheel does on the mind map: plain scrolls (a trackpad pans
 *  both ways), Shift scrolls sideways (a mouse wheel's vertical turn
 *  becomes horizontal), Ctrl is left to markmap's zoom (a trackpad pinch
 *  arrives as Ctrl+wheel), Cmd zooms by a step. */
export function wheelAction(e: Pick<WheelEvent, 'deltaX' | 'deltaY' | 'shiftKey' | 'ctrlKey' | 'metaKey'>):
  | { kind: 'zoom-native' }
  | { kind: 'zoom'; by: number }
  | { kind: 'pan'; dx: number; dy: number } {
  if (e.ctrlKey) return { kind: 'zoom-native' }
  if (e.metaKey) return { kind: 'zoom', by: e.deltaY < 0 ? 1.1 : 1 / 1.1 }
  if (e.shiftKey) return { kind: 'pan', dx: e.deltaX || e.deltaY, dy: 0 }
  return { kind: 'pan', dx: e.deltaX, dy: e.deltaY }
}
