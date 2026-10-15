/** The heights of the left column's areas, Sources and Output format, as a
 *  user dragged them; Outputs takes the rest. null is the stylesheet's
 *  default (Sources and Outputs share, Output format as tall as it needs,
 *  capped). Remembered per user in this browser. Pure, so it is tested. */
export interface LeftSizes {
  sources: number | null
  tiles: number | null
}

/** what each area keeps at least, in px: a few list rows, the tiles row with Create */
export const LEFT_MIN = { sources: 96, tiles: 140, outputs: 96 }
/** the two bars between the areas */
export const ROW_DIVIDERS = 12

const keyOf = (userId: string | null | undefined) => `lasteverlm.leftSizes.${userId ?? 'anonymous'}`

const size = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? Math.round(v) : null)

export function readLeftSizes(storage: Pick<Storage, 'getItem'> | undefined, userId: string | null | undefined): LeftSizes {
  try {
    const raw = storage?.getItem(keyOf(userId))
    if (!raw) return { sources: null, tiles: null }
    const v = JSON.parse(raw) as Partial<Record<keyof LeftSizes, unknown>>
    return { sources: size(v.sources), tiles: size(v.tiles) }
  } catch {
    return { sources: null, tiles: null }
  }
}

export function writeLeftSizes(storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined, userId: string | null | undefined, s: LeftSizes): void {
  try {
    if (s.sources === null && s.tiles === null) storage?.removeItem(keyOf(userId))
    else storage?.setItem(keyOf(userId), JSON.stringify(s))
  } catch {
    // not remembered; the layout still works
  }
}

/** The largest height one area may take: the column minus the other
 *  area as it is now, the Outputs' minimum and the bars. */
export function maxHeight(column: number, other: number, area: keyof LeftSizes): number {
  return Math.max(LEFT_MIN[area], column - other - LEFT_MIN.outputs - ROW_DIVIDERS)
}

export function clampHeight(px: number, area: keyof LeftSizes, max: number): number {
  return Math.round(Math.min(max, Math.max(LEFT_MIN[area], px)))
}
