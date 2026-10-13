import { describe, expect, it } from 'vitest'
import { mapAction } from './mapKeys'

describe('mapAction', () => {
  it('fits with 0 and zooms with plus and minus', () => {
    expect(mapAction('0')).toEqual({ kind: 'fit' })
    expect(mapAction('+')).toEqual({ kind: 'zoom', by: 1.25 })
    expect(mapAction('=')).toEqual({ kind: 'zoom', by: 1.25 })
    expect(mapAction('-')).toEqual({ kind: 'zoom', by: 0.8 })
  })

  it('leaves every other key alone', () => {
    expect(mapAction('a')).toBeNull()
    expect(mapAction('Escape')).toBeNull()
  })
})
