import { describe, expect, it } from 'vitest'
import type { AccountDay, IngestDay, RagDay } from '../api/types'
import { activitySeries, costSeries, dayLabel, defaultRange, hasData, lastDays, modelSeries, outputsByKind, sourcesSeries, total } from './charts'

const acc: AccountDay[] = [
  { day: '2026-10-12', logins: 2, visits: 10, usage_cost_cents: 150, credits_granted_cents: 0 },
  { day: '2026-10-13', logins: 3, visits: 14, usage_cost_cents: 5, credits_granted_cents: 500 },
]
const kinds = { report: 0, quiz: 0, table: 0, mindmap: 0, infographic: 0, audio: 0 }
const rag: RagDay[] = [
  { day: '2026-10-12', messages: 4, outputs: 2, outputs_by_kind: { ...kinds, report: 1, mindmap: 1 } },
  { day: '2026-10-13', messages: 6, outputs: 1, outputs_by_kind: { ...kinds, report: 1 } },
]

describe('chart series', () => {
  it('labels UTC days for the axis', () => {
    expect(dayLabel('2026-10-13')).toBe('Oct 13')
    expect(dayLabel('not a day')).toBe('not a day')
  })

  it('turns cents into euros per day', () => {
    expect(costSeries(acc)).toEqual([
      { day: 'Oct 12', cost: 1.5, granted: 0 },
      { day: 'Oct 13', cost: 0.05, granted: 5 },
    ])
    expect(activitySeries(acc)[1]).toEqual({ day: 'Oct 13', logins: 3, visits: 14 })
  })

  it('sums documents by kind over the period and drops empty kinds', () => {
    expect(outputsByKind(rag)).toEqual([
      { kind: 'report', name: 'Report', value: 2 },
      { kind: 'mindmap', name: 'Mindmap', value: 1 },
    ])
  })

  it('keeps every source kind per day for the stacked bars', () => {
    const days: IngestDay[] = [{ day: '2026-10-13', sources_created: 3, by_kind: { pdf: 1, text: 0, url: 1, image: 1 }, failed: 1 }]
    expect(sourcesSeries(days)).toEqual([{ day: 'Oct 13', pdf: 1, text: 0, url: 1, image: 1, failed: 1 }])
  })

  it('labels models with their kind and sums a series', () => {
    expect(modelSeries({ by_model: [{ model: 'm', kind: 'tts', calls: 3, cost_cents: 640 }], top_users: [] })).toEqual([
      { name: 'm · tts', cost: 6.4, calls: 3 },
    ])
    expect(total(acc, (d) => d.logins)).toBe(5)
  })
})

describe('ranges', () => {
  it('defaults to 7 days while nothing happened before the last week', () => {
    expect(defaultRange([...Array(29).fill(0), 3])).toBe(7)
    expect(defaultRange([1, ...Array(29).fill(0)])).toBe(30)
    expect(defaultRange([0, 0, 2])).toBe(7)
  })

  it('cuts the last days and tells empty series apart', () => {
    expect(lastDays([1, 2, 3, 4], 2)).toEqual([3, 4])
    expect(lastDays([1], 7)).toEqual([1])
    expect(hasData([{ a: 0, b: 0 }, { a: 0, b: 2 }], ['a', 'b'])).toBe(true)
    expect(hasData([{ a: 0, b: 0 }], ['a'])).toBe(false)
  })
})
