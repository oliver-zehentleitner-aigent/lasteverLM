import { describe, expect, it } from 'vitest'
import type { ExchangeRateStatus } from '../api/types'
import { checkedAt, rateLine } from './exchangeRate'

const now = new Date(2026, 9, 14, 16, 0)
const base: ExchangeRateStatus = {
  usd_per_eur: 1.1188,
  mode: 'automatic',
  source: 'ECB',
  rate_date: '2026-10-13',
  last_checked: new Date(2026, 9, 14, 14, 5).toISOString(),
  last_success: new Date(2026, 9, 14, 14, 5).toISOString(),
  last_error: null,
  stale: false,
}

describe('rateLine', () => {
  it('names the ECB day and the last check', () => {
    expect(rateLine(base, now)).toBe('1 EUR = 1.1188 USD · ECB 2026-10-13 · checked 14:05')
  })

  it('says a manual rate is set by hand and leaves out the check', () => {
    expect(rateLine({ ...base, mode: 'manual', source: 'manual' }, now)).toBe('1 EUR = 1.1188 USD · set by hand')
  })

  it('says the seeded value is a starting value', () => {
    expect(rateLine({ ...base, source: 'seed', last_checked: null }, now)).toBe('1 EUR = 1.1188 USD · starting value')
  })

  it('says when there is no rate', () => {
    expect(rateLine({ ...base, usd_per_eur: null, source: 'seed', last_checked: null }, now)).toBe('no exchange rate · starting value')
  })
})

describe('checkedAt', () => {
  it('adds the date for an earlier day', () => {
    expect(checkedAt(new Date(2026, 9, 12, 9, 30).toISOString(), now)).toBe('10/12/2026 09:30')
  })
})
