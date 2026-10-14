import { describe, expect, it } from 'vitest'
import { charge, exactMoney, formatMoney, lastDays } from './money'

describe('money', () => {
  it('shows two decimals from one euro up and up to four below', () => {
    expect(formatMoney(1250)).toBe('€12.50')
    expect(formatMoney(1234.5678)).toBe('€12.35')
    expect(formatMoney(90)).toBe('€0.90')
    expect(formatMoney(62.2125)).toBe('€0.6221')
    expect(formatMoney(62.2377, 'USD')).toBe('$0.6224')
    expect(formatMoney(0.34, 'USD')).toBe('$0.0034')
    expect(formatMoney(0)).toBe('€0.00')
  })

  it('never shows a tiny amount as zero', () => {
    expect(formatMoney(0.001)).toBe('<€0.0001')
  })

  it('keeps the exact value for the tooltip', () => {
    expect(exactMoney(62.2125)).toBe('€0.622125')
  })

  it('makes an inclusive range of days', () => {
    expect(lastDays(7, new Date('2026-10-14T12:00:00Z'))).toEqual({ from: '2026-10-08', to: '2026-10-14' })
  })

  it('prices a cost with a margin and a fee', () => {
    expect(charge(10, 30, 2)).toBeCloseTo(15)
  })
})
