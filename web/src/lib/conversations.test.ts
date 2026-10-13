import { describe, expect, it } from 'vitest'
import { activeAfterClose, renamedTitle } from './conversations'

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

describe('renamedTitle', () => {
  it('saves a changed title, trimmed and with single spaces', () => {
    expect(renamedTitle('  Elbe   questions ', 'Chat 2')).toBe('Elbe questions')
  })

  it('keeps the old title for an empty or unchanged entry', () => {
    expect(renamedTitle('   ', 'Chat 2')).toBeNull()
    expect(renamedTitle('Chat 2', 'Chat 2')).toBeNull()
  })
})
