import { describe, expect, it } from 'vitest'
import { estimateKey, priceLabel } from './estimate'

describe('priceLabel', () => {
  it('rounds the range outwards to whole cents', () => {
    expect(priceLabel({ charge_cents_min: 3.2, charge_cents_max: 8.01 })).toBe('≈ €0.03–€0.09')
  })

  it('shows one price when both ends meet', () => {
    expect(priceLabel({ charge_cents_min: 5, charge_cents_max: 5 })).toBe('≈ €0.05')
  })

  it('says "up to" when the low end is under a cent', () => {
    expect(priceLabel({ charge_cents_min: 0.12, charge_cents_max: 0.87 })).toBe('up to €0.01')
    expect(priceLabel({ charge_cents_min: 0, charge_cents_max: 12.5 })).toBe('up to €0.13')
  })
})

describe('estimateKey', () => {
  it('ignores the order of the fields', () => {
    expect(estimateKey({ kind: 'report', options: { length: 'short', judge: 'low' } })).toBe(
      estimateKey({ options: { judge: 'low', length: 'short' }, kind: 'report' } as never),
    )
  })

  it('tells different options apart', () => {
    expect(estimateKey({ action: 'judge', options: { level: 'low' } })).not.toBe(estimateKey({ action: 'judge', options: { level: 'high' } }))
  })
})
