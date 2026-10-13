/** The little figure walking next to "Generating…": arms swing through
 *  the frames, and every second step it moves one character to the right,
 *  wrapping at the end of its track. */
export const WALKER_FRAMES = ['\\o/', ' o/', ' o ', '\\o '] as const
export const WALKER_TRACK = 8

/** The text for a tick: spaces up to the position, then the figure. */
export function walkerAt(tick: number): string {
  const frame = WALKER_FRAMES[tick % WALKER_FRAMES.length]
  const pos = Math.floor(tick / 2) % WALKER_TRACK
  return ' '.repeat(pos) + frame
}
