import { describe, expect, it } from 'vitest'
import type { Output } from '../api/types'
import { kindsPresent, optionsBrief, sortOutputs, whenLabel } from './outputsList'

const out = (id: string, kind: Output['kind'], created_at: string, status: Output['status'] = 'ready', options: Output['options'] = {}): Output => ({
  id,
  notebook_id: 'n',
  kind,
  title: id,
  content: null,
  status,
  error: null,
  share_token: null,
  source_id: null,
  created_at,
  options,
})

const list = [
  out('a', 'report', '2026-10-13T10:00:00Z', 'ready', { language: 'de' }),
  out('b', 'audio', '2026-10-13T12:00:00Z', 'processing', { language: 'en', voice: 'vivian', speed: 1 }),
  out('c', 'report', '2026-10-13T11:00:00Z', 'failed'),
  out('d', 'quiz', '2026-10-13T09:00:00Z', 'ready', { language: 'de' }),
]
const ids = (l: Output[]) => l.map((o) => o.id)

describe('sortOutputs', () => {
  it('orders newest first by default and oldest on request', () => {
    expect(ids(sortOutputs(list, 'newest'))).toEqual(['b', 'c', 'a', 'd'])
    expect(ids(sortOutputs(list, 'oldest'))).toEqual(['d', 'a', 'c', 'b'])
  })

  it('groups by kind, language and status, newest first inside a group', () => {
    expect(ids(sortOutputs(list, 'kind'))).toEqual(['c', 'a', 'd', 'b'])
    expect(ids(sortOutputs(list, 'language'))).toEqual(['a', 'd', 'b', 'c'])
    expect(ids(sortOutputs(list, 'status'))).toEqual(['b', 'c', 'a', 'd'])
  })

  it('lists the kinds present in tile order', () => {
    expect(kindsPresent(list)).toEqual(['report', 'quiz', 'audio'])
  })
})

describe('whenLabel', () => {
  const now = new Date('2026-10-13T12:30:00Z')
  it('is relative within a day and absolute after', () => {
    expect(whenLabel('2026-10-13T12:16:00Z', now)).toBe('14 min. ago')
    expect(whenLabel('2026-10-13T09:30:00Z', now)).toBe('3 hr. ago')
    expect(whenLabel('2026-10-13T12:29:50Z', now)).toBe('this minute')
    expect(whenLabel('2026-10-11T12:00:00Z', now)).not.toContain('ago')
  })
})

describe('optionsBrief', () => {
  it('shows the language and, for audio, the voice', () => {
    expect(optionsBrief(list[1], (v) => v[0].toUpperCase() + v.slice(1))).toBe('EN · Vivian')
    expect(optionsBrief(list[0], (v) => v)).toBe('DE')
    expect(optionsBrief(list[2], (v) => v)).toBe('')
  })
})
