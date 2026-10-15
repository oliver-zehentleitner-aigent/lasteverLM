import { describe, expect, it } from 'vitest'
import { firstSelection } from './firstRun'

describe('firstSelection', () => {
  it('keeps the notebook that was open', () => {
    expect(firstSelection(['a', 'b'], 'b', true)).toEqual({ select: 'b', createFirst: false })
  })

  it('opens the first one otherwise: a new user\'s starter notebook', () => {
    expect(firstSelection(['starter'], null, true)).toEqual({ select: 'starter', createFirst: false })
    // the last notebook of an account deleted in this browser is not in the list
    expect(firstSelection(['starter'], 'gone', true)).toEqual({ select: 'starter', createFirst: false })
  })

  it('makes a first notebook only when there is none and the tour is still to come', () => {
    expect(firstSelection([], null, true)).toEqual({ select: null, createFirst: true })
    expect(firstSelection([], null, false)).toEqual({ select: null, createFirst: false })
  })
})
