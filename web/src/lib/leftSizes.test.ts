import { describe, expect, it } from 'vitest'
import { LEFT_MIN, clampHeight, maxHeight, readLeftSizes, writeLeftSizes } from './leftSizes'

function memory() {
  const m = new Map<string, string>()
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), m }
}

describe('left column sizes', () => {
  it('are remembered per user and cleared when both are the default again', () => {
    const s = memory()
    writeLeftSizes(s, 'u1', { sources: 220.4, tiles: null })
    expect(readLeftSizes(s, 'u1')).toEqual({ sources: 220, tiles: null })
    expect(readLeftSizes(s, 'u2')).toEqual({ sources: null, tiles: null })
    writeLeftSizes(s, 'u1', { sources: null, tiles: null })
    expect(s.m.size).toBe(0)
  })

  it('read anything broken as the default', () => {
    const s = memory()
    s.setItem('lasteverlm.leftSizes.u1', '{nope')
    expect(readLeftSizes(s, 'u1')).toEqual({ sources: null, tiles: null })
    s.setItem('lasteverlm.leftSizes.u1', JSON.stringify({ sources: -5, tiles: 'x' }))
    expect(readLeftSizes(s, 'u1')).toEqual({ sources: null, tiles: null })
    expect(readLeftSizes({ getItem: () => { throw new Error('blocked') } }, 'u1')).toEqual({ sources: null, tiles: null })
  })

  it('keep every area at its minimum and Outputs visible', () => {
    // a 900 px column with Output format at 300: Sources may take 900 - 300 - 96 - 12
    expect(maxHeight(900, 300, 'sources')).toBe(492)
    expect(clampHeight(800, 'sources', maxHeight(900, 300, 'sources'))).toBe(492)
    expect(clampHeight(10, 'tiles', 500)).toBe(LEFT_MIN.tiles)
    // a column too short for everything still leaves the area its minimum
    expect(maxHeight(200, 300, 'tiles')).toBe(LEFT_MIN.tiles)
  })
})
