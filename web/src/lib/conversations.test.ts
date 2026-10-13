import { describe, expect, it } from 'vitest'
import { activeAfterClose } from './conversations'

describe('activeAfterClose', () => {
  const ids = ['a', 'b', 'c']

  it('keeps the active tab when another one closes', () => {
    expect(activeAfterClose(ids, 'a', 'b')).toBe('b')
  })

  it('moves to the right neighbour when the active tab closes', () => {
    expect(activeAfterClose(ids, 'b', 'b')).toBe('c')
  })

  it('moves to the left neighbour when the last tab closes', () => {
    expect(activeAfterClose(ids, 'c', 'c')).toBe('b')
  })

  it('is null when no tab is left', () => {
    expect(activeAfterClose(['a'], 'a', 'a')).toBeNull()
  })
})
