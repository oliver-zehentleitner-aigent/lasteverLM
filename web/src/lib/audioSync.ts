/** The transcript entry being spoken at `time`: start <= time < end; -1
 *  when the entries carry no timings (older audio) or none matches. Pure,
 *  so it is tested. */
export function activeTurn(turns: readonly { start?: number; end?: number }[], time: number): number {
  for (let i = 0; i < turns.length; i++) {
    const { start, end } = turns[i]
    if (start == null || end == null) return -1
    if (start <= time && time < end) return i
  }
  return -1
}

/** Whether the transcript can follow the player at all. */
export const timed = (turns: readonly { start?: number; end?: number }[]) => turns.length > 0 && turns.every((x) => x.start != null && x.end != null)
