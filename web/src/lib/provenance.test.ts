import { describe, expect, it } from 'vitest'
import { chunkPosition, claimFor, highlightPassage, similarityLabel, similarityPercent } from './provenance'

describe('provenance labels', () => {
  it('shows the 0-based index as a position', () => {
    expect(chunkPosition(11, 43)).toBe('chunk 12 of 43')
    expect(chunkPosition(null, 43)).toBeNull()
    expect(chunkPosition(undefined, undefined)).toBeNull()
  })

  it('formats similarity with two decimals and clamps the bar', () => {
    expect(similarityLabel(0.734)).toBe('0.73')
    expect(similarityLabel(null)).toBeNull()
    expect(similarityPercent(0.734)).toBe(73)
    expect(similarityPercent(1.4)).toBe(100)
  })
})

describe('claimFor', () => {
  const answer = 'The Danube is about 2850 km long [1]. It flows through ten countries [1, 2]. Vienna lies on it.'

  it('finds the sentence carrying the marker, grouped markers included', () => {
    expect(claimFor(answer, 1)).toBe('The Danube is about 2850 km long.')
    expect(claimFor(answer, 2)).toBe('It flows through ten countries.')
    expect(claimFor(answer, 3)).toBe('')
  })
})

describe('highlightPassage', () => {
  const chunk = 'The Danube is the second-longest river in Europe. It flows through ten countries, more than any other river. Vienna is a capital on it.'

  it('highlights the chunk sentence sharing the most words with the claim', () => {
    const p = highlightPassage(chunk, 'It flows through ten countries')
    expect(p.match).toBe(' It flows through ten countries, more than any other river.')
    expect(p.before + p.match + p.after).toBe(chunk)
  })

  it('highlights nothing without overlap', () => {
    expect(highlightPassage(chunk, 'photosynthesis')).toEqual({ before: chunk, match: '', after: '' })
  })
})
