import { describe, expect, it } from 'vitest'
import { activeTurn, timed } from './audioSync'

const turns = [
  { start: 0, end: 4.2 },
  { start: 4.2, end: 9.75 },
  { start: 9.75, end: 15 },
]

describe('activeTurn', () => {
  it('finds the entry with start <= time < end', () => {
    expect(activeTurn(turns, 0)).toBe(0)
    expect(activeTurn(turns, 4.2)).toBe(1)
    expect(activeTurn(turns, 14.99)).toBe(2)
  })

  it('is -1 past the end and without timings', () => {
    expect(activeTurn(turns, 15)).toBe(-1)
    expect(activeTurn([{}, {}], 1)).toBe(-1)
  })
})

describe('timed', () => {
  it('needs times on every entry', () => {
    expect(timed(turns)).toBe(true)
    expect(timed([{ start: 0, end: 1 }, {}])).toBe(false)
    expect(timed([])).toBe(false)
  })
})
