import { describe, expect, it } from 'vitest'
import { keptRefresh } from './urlRefresh'

describe('keptRefresh', () => {
  it('keeps only pages still selected, by library id', () => {
    expect(keptRefresh(new Set(['l1', 'l2']), [{ id: 's1', library_id: 'l1' }, { id: 's3', library_id: 'l3' }])).toEqual(['l1'])
  })
})
