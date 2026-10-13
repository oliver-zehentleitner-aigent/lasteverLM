import { describe, expect, it } from 'vitest'
import { tabForKey } from './tabs'

describe('tabForKey', () => {
  const ids = ['a', 'b', 'c']

  it('steps with the arrows and wraps around', () => {
    expect(tabForKey(ids, 'a', 'ArrowRight')).toBe('b')
    expect(tabForKey(ids, 'c', 'ArrowRight')).toBe('a')
    expect(tabForKey(ids, 'a', 'ArrowLeft')).toBe('c')
  })

  it('jumps with Home and End and ignores other keys', () => {
    expect(tabForKey(ids, 'b', 'Home')).toBe('a')
    expect(tabForKey(ids, 'b', 'End')).toBe('c')
    expect(tabForKey(ids, 'b', 'Enter')).toBeNull()
    expect(tabForKey([], null, 'ArrowRight')).toBeNull()
  })
})
