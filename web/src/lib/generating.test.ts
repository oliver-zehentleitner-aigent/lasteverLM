import { describe, expect, it } from 'vitest'
import { elapsedLabel, phaseLabel } from './generating'

describe('elapsedLabel', () => {
  const start = '2026-10-15T10:00:00Z'
  const at = (s: number) => new Date(start).getTime() + s * 1000

  it('counts minutes and seconds, hours past an hour', () => {
    expect(elapsedLabel(start, at(102))).toBe('1:42')
    expect(elapsedLabel(start, at(5))).toBe('0:05')
    expect(elapsedLabel(start, at(3725))).toBe('1:02:05')
  })

  it('is never negative, and nothing for a bad time', () => {
    expect(elapsedLabel(start, at(-30))).toBe('0:00')
    expect(elapsedLabel('nope', at(1))).toBeNull()
  })
})

describe('phaseLabel', () => {
  const since = '2026-10-15T10:00:00Z'
  it('says what the worker sent, with its counters', () => {
    expect(phaseLabel({ step: 'judging', since, n: 2, of: 3 })).toBe('Judging, round 2 of 3')
    expect(phaseLabel({ step: 'revising', since, n: 1 })).toBe('Revising round 1')
    expect(phaseLabel({ step: 'synthesizing_speech', since, n: 3, of: 8 })).toBe('Speech, segment 3 of 8')
    expect(phaseLabel({ step: 'retry', since, n: 2, of: 3, error: 'glm-5.3: timeout' })).toBe('Attempt 2 of 3 follows (glm-5.3: timeout)')
    expect(phaseLabel({ step: 'waiting_for_sources', since, sources: ['a.pdf', 'b.pdf'] })).toBe('Reading the sources: a.pdf, b.pdf')
    expect(phaseLabel({ step: 'writing', since })).toBe('Writing')
  })

  it('shows a step it does not know by its name', () => {
    expect(phaseLabel({ step: 'polishing', since } as never)).toBe('polishing')
  })
})
