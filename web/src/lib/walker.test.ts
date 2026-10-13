import { describe, expect, it } from 'vitest'
import { WALKER_TRACK, walkerAt } from './walker'

describe('walkerAt', () => {
  it('swings its arms and steps right every second tick', () => {
    expect(walkerAt(0)).toBe('\\o/')
    expect(walkerAt(1)).toBe(' o/')
    expect(walkerAt(2)).toBe('  o ')
    expect(walkerAt(3)).toBe(' \\o ')
  })

  it('wraps at the end of its track', () => {
    expect(walkerAt(2 * WALKER_TRACK)).toBe(walkerAt(0))
  })
})
