import type { AccountDay, AccountUsage, IngestDay, OutputKind, RagDay } from '../api/types'
import { language } from '../i18n'
import { formFor, SOURCE_FORMS } from './outputs'

/** "Oct 13" ("13. Okt." in German) for a UTC date "2026-10-13"; the axis labels of every chart. */
export function dayLabel(day: string): string {
  const d = new Date(`${day}T00:00:00Z`)
  return Number.isNaN(d.getTime()) ? day : d.toLocaleDateString(language(), { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

const euros = (cents: number) => Math.round(cents) / 100

/** Cost and granted credit per day, in euros, for the bar chart. */
export function costSeries(days: readonly AccountDay[]) {
  return days.map((d) => ({ day: dayLabel(d.day), cost: euros(d.usage_cost_cents), granted: euros(d.credits_granted_cents) }))
}

/** Logins and page visits per day, for the line chart. */
export function activitySeries(days: readonly AccountDay[]) {
  return days.map((d) => ({ day: dayLabel(d.day), logins: d.logins, visits: d.visits }))
}

/** Chat messages and created documents per day. */
export function ragActivitySeries(days: readonly RagDay[]) {
  return days.map((d) => ({ day: dayLabel(d.day), messages: d.messages, documents: d.outputs }))
}

/** Documents of the whole period by kind, for the donut; empty kinds left out. */
export function outputsByKind(days: readonly RagDay[]) {
  const totals = new Map<OutputKind, number>()
  for (const d of days) {
    for (const [kind, n] of Object.entries(d.outputs_by_kind) as [OutputKind, number][]) {
      totals.set(kind, (totals.get(kind) ?? 0) + n)
    }
  }
  return [...totals]
    .filter(([, n]) => n > 0)
    .map(([kind, value]) => ({ kind, name: formFor(kind).label, value }))
}

/** The source kinds as series keys, in the wizard's order. */
export const SOURCE_SERIES = SOURCE_FORMS.map((f) => ({
  key: f.kind,
  get label() {
    return f.label
  },
}))

/** Sources created per day split by kind, for the stacked bars. */
export function sourcesSeries(days: readonly IngestDay[]) {
  return days.map((d) => ({ day: dayLabel(d.day), ...d.by_kind, failed: d.failed }))
}

/** Cost by model in euros, label with its kind, for the horizontal bars. */
export function modelSeries(usage: AccountUsage) {
  return usage.by_model.map((m) => ({ name: `${m.model} · ${m.kind}`, cost: euros(m.cost_cents), calls: m.calls }))
}

/** Sum of one numeric field over a series, for a chart's headline. */
export function total<T>(rows: readonly T[], pick: (r: T) => number): number {
  return rows.reduce((a, r) => a + pick(r), 0)
}

/** The ranges the overview offers; the series are loaded for the longest. */
export const RANGES = [7, 30] as const
export type Range = (typeof RANGES)[number]

/** 7 days when everything happened in the last week (a young deployment),
 *  so the charts are not 23 empty days and a bar; 30 otherwise. `activity`
 *  is one total per day, oldest first, today last. */
export function defaultRange(activity: readonly number[]): Range {
  const older = activity.slice(0, Math.max(0, activity.length - 7))
  return older.some((v) => v > 0) ? 30 : 7
}

/** The last `n` days of a series loaded for a longer range. */
export function lastDays<T>(rows: readonly T[], n: number): T[] {
  return rows.slice(Math.max(0, rows.length - n))
}

/** Whether any row has a non-zero value in one of the keys. */
export function hasData<T extends object>(rows: readonly T[], keys: readonly (keyof T)[]): boolean {
  return rows.some((r) => keys.some((k) => Number(r[k]) > 0))
}
