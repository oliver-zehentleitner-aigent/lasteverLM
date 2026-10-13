import { describe, expect, it } from 'vitest'
import { bestMatchIndex, firstLine } from './locate'

describe('bestMatchIndex', () => {
  const blocks = ['Introduction', 'The Oder forms part of the border between Germany and Poland.', 'It is about 840 km long.', 'Oder River']

  it('picks the block sharing the most words with the chunk', () => {
    expect(bestMatchIndex(blocks, 'The Oder river forms part of the border between Germany and Poland.')).toBe(1)
  })

  it('takes a short label when all of its words are in the chunk', () => {
    expect(bestMatchIndex(['Elbe', 'Oder River'], 'Oder River: Geography and Border')).toBe(1)
  })

  it('finds nothing without real overlap', () => {
    expect(bestMatchIndex(blocks, 'Photosynthesis in green plants')).toBe(-1)
    expect(bestMatchIndex([], 'anything')).toBe(-1)
  })
})

describe('firstLine', () => {
  it('drops list and heading marks', () => {
    expect(firstLine('Oder River: Geography and Border\n- Oder River')).toBe('Oder River: Geography and Border')
    expect(firstLine('\n  - Oder River\n  - Length')).toBe('Oder River')
    expect(firstLine('## Overview\ntext')).toBe('Overview')
  })
})
