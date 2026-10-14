import { describe, expect, it } from 'vitest'
import { charge, formatMoney, lastDays } from './money'

describe('money', () => {
  it('shows whole cents with two decimals and fractions of a cent finer', () => {
    expect(formatMoney(1250)).toBe('€12.50')
    expect(formatMoney(0.34, 'USD')).toBe('$0.0034')
    expect(formatMoney(12.3456)).toBe('€0.123456')
    expect(formatMoney(0)).toBe('€0.00')
  })

  it('makes an inclusive range of days', () => {
    expect(lastDays(7, new Date('2026-10-14T12:00:00Z'))).toEqual({ from: '2026-10-08', to: '2026-10-14' })
  })

  it('prices a cost with a margin and a fee', () => {
    expect(charge(10, 30, 2)).toBeCloseTo(15)
  })
})
