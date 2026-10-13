/** The share of the right column the viewer takes above the chat. */
export const DEFAULT_VIEWER_RATIO = 0.5
export const MIN_VIEWER_RATIO = 0.2
export const MAX_VIEWER_RATIO = 0.85
const KEY = 'lasteverlm.viewerRatio'

export function clampRatio(r: number): number {
  if (!Number.isFinite(r)) return DEFAULT_VIEWER_RATIO
  return Math.min(MAX_VIEWER_RATIO, Math.max(MIN_VIEWER_RATIO, r))
}

/** Pointer position inside the column, as a ratio. */
export function ratioFromPointer(clientY: number, top: number, height: number): number {
  return height > 0 ? clampRatio((clientY - top) / height) : DEFAULT_VIEWER_RATIO
}

/** The stored ratio of this browser. Storage can be missing or throw
 *  (private window, blocked site data); the default is used then. */
export function readRatio(storage: Pick<Storage, 'getItem'> | undefined): number {
  try {
    const v = storage?.getItem(KEY)
    return v === null || v === undefined ? DEFAULT_VIEWER_RATIO : clampRatio(Number(v))
  } catch {
    return DEFAULT_VIEWER_RATIO
  }
}

export function writeRatio(storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined, r: number | null): void {
  try {
    if (r === null) storage?.removeItem(KEY)
    else storage?.setItem(KEY, String(clampRatio(r)))
  } catch {
    // not remembered; the layout still works
  }
}

/** `window.localStorage` itself can throw when site data is blocked. */
export function browserStorage(): Storage | undefined {
  try {
    return window.localStorage
  } catch {
    return undefined
  }
}
