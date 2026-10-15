import { language } from '../i18n'

/** Cents in a currency, by one rule for every money cell: two decimals
 *  from 1 € (or $1) up; below that at least two and up to four decimals
 *  (a single model call costs fractions of a cent): €0.90, €0.6221,
 *  $0.0034. An amount too small for four decimals is "<€0.0001", never
 *  €0.0000. `exactMoney` has the full value for the tooltip. */
export function formatMoney(cents: number, currency: 'EUR' | 'USD' = 'EUR'): string {
  const value = cents / 100
  const small = Math.abs(value) < 1
  if (small && value !== 0 && Math.abs(value) < 0.00005) {
    return `<${(value < 0 ? -0.0001 : 0.0001).toLocaleString(language(), { style: 'currency', currency, minimumFractionDigits: 4 })}`
  }
  return value.toLocaleString(language(), { style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: small ? 4 : 2 })
}

/** The amount as stored, to a millionth of the currency, for a tooltip. */
export function exactMoney(cents: number, currency: 'EUR' | 'USD' = 'EUR'): string {
  return (cents / 100).toLocaleString(language(), { style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: 8 })
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

/** The costs of a range: the model costs and the infrastructure lines in
 *  EUR; a USD line without a rate cannot be added and is counted apart. */
export function totalCosts(modelCents: number, infra: readonly { amount_eur_cents: number | null }[]): { total: number; model: number; infra: number; notIncluded: number } {
  const known = infra.filter((x) => x.amount_eur_cents !== null)
  const infraCents = known.reduce((a, x) => a + (x.amount_eur_cents ?? 0), 0)
  return { total: modelCents + infraCents, model: modelCents, infra: infraCents, notIncluded: infra.length - known.length }
}
