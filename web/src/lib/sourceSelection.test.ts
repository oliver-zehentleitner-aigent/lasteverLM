import { describe, expect, it } from 'vitest'
import { madeFrom, readExcluded, selection, toggled, writeExcluded } from './sourceSelection'

function memory() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    m,
  }
}

describe('selection', () => {
  it('sends no ids while everything is selected', () => {
    expect(selection(['a', 'b'], new Set())).toEqual({ selected: 2, total: 2, sourceIds: undefined })
  })

  it('sends the selected ids once one is off, ignoring ids that are gone', () => {
    expect(selection(['a', 'b', 'c'], new Set(['b', 'gone']))).toEqual({ selected: 2, total: 3, sourceIds: ['a', 'c'] })
  })

  it('sends an empty list when none is selected', () => {
    expect(selection(['a'], new Set(['a'])).sourceIds).toEqual([])
  })
})

describe('toggled', () => {
  it('turns a source off and on again', () => {
    const off = toggled(new Set(), 'a')
    expect(off.has('a')).toBe(true)
    expect(toggled(off, 'a').has('a')).toBe(false)
  })
})

describe('storage', () => {
  it('remembers the sources turned off per notebook', () => {
    const s = memory()
    writeExcluded(s, 'nb1', new Set(['a']))
    expect([...readExcluded(s, 'nb1')]).toEqual(['a'])
    expect(readExcluded(s, 'nb2').size).toBe(0)
  })

  it('forgets the entry when everything is on again', () => {
    const s = memory()
    writeExcluded(s, 'nb1', new Set(['a']))
    writeExcluded(s, 'nb1', new Set())
    expect(s.m.size).toBe(0)
  })

  it('survives broken or missing storage', () => {
    const s = memory()
    s.setItem('lasteverlm.sources-off.nb1', '{not json')
    expect(readExcluded(s, 'nb1').size).toBe(0)
    expect(readExcluded(undefined, 'nb1').size).toBe(0)
    const throwing = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') }, removeItem: () => {} }
    expect(readExcluded(throwing, 'nb1').size).toBe(0)
    expect(() => writeExcluded(throwing, 'nb1', new Set(['a']))).not.toThrow()
  })
})

describe('madeFrom', () => {
  const sources = [
    { id: 'a', name: 'a.pdf' },
    { id: 'b', name: 'b.txt' },
  ]

  it('is nothing when all sources were used', () => {
    expect(madeFrom(undefined, sources)).toBeNull()
    expect(madeFrom([], sources)).toBeNull()
  })

  it('names the sources still there and counts the removed ones', () => {
    expect(madeFrom(['b', 'gone'], sources)).toEqual({ n: 2, names: ['b.txt'], removed: 1 })
  })
})
