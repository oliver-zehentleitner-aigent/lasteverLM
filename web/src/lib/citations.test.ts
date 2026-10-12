import { describe, expect, it } from 'vitest'
import { splitCitations } from './citations'

describe('splitCitations', () => {
  it('turns known markers into cite parts and keeps the text around them', () => {
    const parts = splitCitations('Water boils at 100 C [1], lower at altitude [2].', new Set([1, 2]))
    expect(parts).toEqual([
      { kind: 'text', text: 'Water boils at 100 C ' },
      { kind: 'cite', n: 1 },
      { kind: 'text', text: ', lower at altitude ' },
      { kind: 'cite', n: 2 },
      { kind: 'text', text: '.' },
    ])
  })

  it('leaves a marker without a matching citation as plain text', () => {
    const parts = splitCitations('Claim [3].', new Set([1]))
    expect(parts).toEqual([{ kind: 'text', text: 'Claim [3].' }])
  })

  it('handles adjacent markers and an answer with none', () => {
    expect(splitCitations('A [1][2]', new Set([1, 2]))).toEqual([
      { kind: 'text', text: 'A ' },
      { kind: 'cite', n: 1 },
      { kind: 'cite', n: 2 },
    ])
    expect(splitCitations('No sources.', new Set())).toEqual([{ kind: 'text', text: 'No sources.' }])
  })
})

describe('splitCitations with grouped markers', () => {
  it('splits [1, 2, 5] into one marker per known number', () => {
    expect(splitCitations('Ten countries [1, 2, 5].', new Set([1, 2, 5]))).toEqual([
      { kind: 'text', text: 'Ten countries ' },
      { kind: 'cite', n: 1 },
      { kind: 'cite', n: 2 },
      { kind: 'cite', n: 5 },
      { kind: 'text', text: '.' },
    ])
  })
  it('keeps unknown numbers of a group as text and cites the rest', () => {
    expect(splitCitations('A [1, 3].', new Set([1]))).toEqual([
      { kind: 'text', text: 'A ' },
      { kind: 'text', text: '[3]' },
      { kind: 'cite', n: 1 },
      { kind: 'text', text: '.' },
    ])
  })
  it('leaves a group with no known number untouched', () => {
    expect(splitCitations('A [7, 8].', new Set([1]))).toEqual([{ kind: 'text', text: 'A [7, 8].' }])
  })
})
