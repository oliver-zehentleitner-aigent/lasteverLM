import type { Flashcard } from '../api/types'

export type CardMark = 'knew' | 'again'

/** The cards as Anki imports them: one per line, front;back, each field
 *  in double quotes with inner quotes doubled, line breaks kept inside the
 *  quotes. Pure, so it is tested. */
export function toAnkiCsv(cards: readonly Flashcard[]): string {
  const field = (s: string) => `"${s.replace(/"/g, '""')}"`
  return cards.map((c) => `${field(c.front)};${field(c.back)}`).join('\n') + '\n'
}

/** A new order for the cards (Fisher–Yates); `random` is injectable for tests. */
export function shuffled(n: number, random: () => number = Math.random): number[] {
  const order = Array.from({ length: n }, (_, i) => i)
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[order[i], order[j]] = [order[j], order[i]]
  }
  return order
}

/** "7 known · 2 again · 6 open" as numbers, from this session's marks. */
export function progress(total: number, marks: ReadonlyMap<number, CardMark>): { knew: number; again: number; open: number } {
  let knew = 0
  let again = 0
  for (const m of marks.values()) {
    if (m === 'knew') knew += 1
    else again += 1
  }
  return { knew, again, open: Math.max(0, total - knew - again) }
}
