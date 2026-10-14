import { describe, expect, it } from 'vitest'
import type { Flashcard } from '../api/types'
import { progress, shuffled, toAnkiCsv } from './flashcards'

describe('toAnkiCsv', () => {
  it('writes front;back with quotes doubled and line breaks kept', () => {
    const cards: Flashcard[] = [
      { front: 'What is "dead reckoning"?', back: 'A position from a known start;\nspeed and heading.' },
      { front: 'Fog', back: 'Dense' },
    ]
    expect(toAnkiCsv(cards)).toBe('"What is ""dead reckoning""?";"A position from a known start;\nspeed and heading."\n"Fog";"Dense"\n')
  })
})

describe('shuffled', () => {
  it('is a permutation of all cards', () => {
    const order = shuffled(10)
    expect([...order].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
  })

  it('follows the random source', () => {
    expect(shuffled(3, () => 0)).toEqual([1, 2, 0])
  })
})

describe('progress', () => {
  it('counts known, again and open', () => {
    expect(progress(5, new Map([[0, 'knew'], [2, 'again'], [3, 'knew']]))).toEqual({ knew: 2, again: 1, open: 2 })
  })
})
