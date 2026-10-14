import { language } from '../i18n'

/** Cents in a currency, two decimals, or up to four more for amounts below
 *  a cent's worth of precision (a single model call costs fractions of a
 *  cent): 0.34 cents shows as $0.0034, not $0.00. */
export function formatMoney(cents: number, currency: 'EUR' | 'USD' = 'EUR'): string {
  const value = cents / 100
  const fine = Math.abs(cents) < 100 && !Number.isInteger(cents)
  return value.toLocaleString(language(), {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: fine ? 6 : 2,
  })
}

/** "2026-10-14": a date as the finance endpoints take it, UTC. */
export function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10)
}

/** The range ending today with `days` days in it, inclusive. */
export function lastDays(days: number, today: Date = new Date()): { from: string; to: string } {
  const from = new Date(today.getTime() - (days - 1) * 86_400_000)
  return { from: isoDay(from), to: isoDay(today) }
}

/** A margin and a fixed fee applied to a cost, as core prices an action. */
export function charge(costCents: number, marginPct: number, fixedCents: number): number {
  return costCents * (1 + marginPct / 100) + fixedCents
}
