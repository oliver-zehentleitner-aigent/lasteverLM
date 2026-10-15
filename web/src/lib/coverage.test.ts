import { describe, expect, it } from 'vitest'
import { coverageLine, unusedSources } from './coverage'

const c = {
  selected: 5,
  cited: 4,
  sources: [
    { source_id: 'a', name: 'a.pdf', cited: true, reason: null },
    { source_id: 'b', name: 'b.pdf', cited: false, reason: 'covers another period' },
    { source_id: 'c', name: 'c.txt', cited: false, reason: null },
  ],
}

describe('coverage', () => {
  it('counts the cited of the selected sources', () => {
    expect(coverageLine(c)).toBe('4 of 5 sources used')
    expect(coverageLine({ ...c, selected: 0 })).toBeNull()
    expect(coverageLine(undefined)).toBeNull()
  })
  it('lists the unused ones with the reason given, or says none was', () => {
    expect(unusedSources(c)).toEqual([
      { name: 'b.pdf', reason: 'covers another period' },
      { name: 'c.txt', reason: 'not used, no reason given' },
    ])
    expect(unusedSources(null)).toEqual([])
  })
})
