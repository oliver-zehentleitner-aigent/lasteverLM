import { describe, expect, it } from 'vitest'
import type { PublicPriceRow } from '../api/types'
import { actionLabel, formatPrice, groupPrices, priceText, typicalText, unitLabel } from './prices'

const row = (action: string, unit = 'output'): PublicPriceRow => ({ action, unit, price_per_unit_cents: 1, typical_cents: null, count: 9, model: null })

describe('groupPrices', () => {
  it('groups by action and orders sources and outputs as the app does', () => {
    const groups = groupPrices([row('judge'), row('output:quiz'), row('source:url'), row('chat_answer'), row('output:report'), row('source:pdf')])
    expect(groups.map((g) => g.group)).toEqual(['sources', 'chat', 'outputs', 'extras'])
    expect(groups[0].rows.map((r) => r.action)).toEqual(['source:pdf', 'source:url'])
    expect(groups[2].rows.map((r) => r.action)).toEqual(['output:report', 'output:quiz'])
  })

  it('keeps an action it does not know, last in extras', () => {
    const groups = groupPrices([row('something_new'), row('judge')])
    expect(groups[0].rows.map((r) => r.action)).toEqual(['judge', 'something_new'])
  })

  it('puts the judge per level first in extras, low to high', () => {
    const groups = groupPrices([row('chart_propose'), row('judge:high'), row('judge:low'), row('judge:medium')])
    expect(groups[0].rows.map((r) => r.action)).toEqual(['judge:low', 'judge:medium', 'judge:high', 'chart_propose'])
  })

  it('puts a way of reading a kind right after it', () => {
    const groups = groupPrices([row('source:url'), row('source:pdf:vision'), row('source:pdf')])
    expect(groups[0].rows.map((r) => r.action)).toEqual(['source:pdf', 'source:pdf:vision', 'source:url'])
  })

  it('leaves out empty groups', () => {
    expect(groupPrices([row('chat_answer')]).map((g) => g.group)).toEqual(['chat'])
  })
})

describe('labels', () => {
  it('names actions and units, and falls back to the code', () => {
    expect(actionLabel('output:report')).toBe('Report')
    expect(actionLabel('source:pdf')).toBe('PDF (Text)')
    expect(actionLabel('source:pdf:vision')).toBe('PDF (Vision)')
    expect(actionLabel('judge')).toBe('Check with a judge')
    expect(actionLabel('judge:medium')).toBe('Judge, medium')
    expect(actionLabel('brand_new')).toBe('brand_new')
    expect(unitLabel('audio_minute')).toBe('per minute of audio')
    expect(unitLabel('page')).toBe('per page')
  })
})

describe('formatPrice', () => {
  it('shows whole cents from ten cents up', () => {
    expect(formatPrice(12.3456)).toBe('€0.12')
    expect(formatPrice(250)).toBe('€2.50')
  })

  it('keeps two significant digits below ten cents', () => {
    expect(formatPrice(0.3456)).toBe('€0.0035')
    expect(formatPrice(3.456)).toBe('€0.035')
  })
})

describe('typicalText', () => {
  it('gives the range and the median, or null without experience', () => {
    expect(typicalText({ ...row('output:report'), typical_cents: { p25: 12, median: 20, p75: 31 } })).toBe('€0.12–€0.31, median €0.20')
    expect(typicalText(row('output:report'))).toBeNull()
  })
})

describe('priceText', () => {
  it('shows a range when min and max differ, with the per-source part and the estimate', () => {
    expect(priceText({ ...row('source:pdf:vision', 'page'), price_per_unit_cents: 3, price_min_cents: 1, price_max_cents: 5, per_source_cents: 1, estimated: true })).toEqual({
      price: '€0.01–€0.05',
      perSource: '+ €0.01 per source',
      estimated: true,
    })
  })

  it('shows one price when the range collapses or is absent', () => {
    expect(priceText({ ...row('chat_answer', 'question'), price_per_unit_cents: 0.34, price_min_cents: 0.341, price_max_cents: 0.344 }).price).toBe('€0.0034')
    expect(priceText(row('output:report')).price).toBe('€0.01')
  })

  it('has no price when none could be made', () => {
    expect(priceText({ ...row('output:report'), price_per_unit_cents: null, estimated: true })).toEqual({ price: null, perSource: null, estimated: false })
  })
})
