import type { ChartPoint, ChartSpec } from '../api/types'
import { t, tn } from '../i18n'

/** A chart output's arithmetic: rows for recharts, the check as numbers,
 *  CSV. Pure, so it is tested. */

/** Every value of a chart, with its series. */
export function allPoints(c: ChartSpec): { series: string; point: ChartPoint }[] {
  return c.series.flatMap((s) => s.points.map((point) => ({ series: s.name, point })))
}

/** How many values the check backed, of all; a computed value counts as
 *  backed when it is shown as computed. */
export function supportCount(charts: readonly ChartSpec[]): { supported: number; derived: number; total: number } {
  const points = charts.flatMap(allPoints)
  return {
    supported: points.filter((p) => p.point.support === 'supported').length,
    derived: points.filter((p) => p.point.support === 'derived').length,
    total: points.length,
  }
}

/** "8 of 10 values supported · 1 computed". */
export function supportLine(charts: readonly ChartSpec[]): string | null {
  const c = supportCount(charts)
  if (c.total === 0) return null
  const line = tn('chartOut.supported', c.total, { supported: c.supported })
  return c.derived > 0 ? `${line} · ${t('chartOut.computedN', { n: c.derived })}` : line
}


/** recharts' rows for bar, line and stacked bar: one per x in first-seen
 *  order, a field per series (`s0`, `s1`, …; names may clash with keys). */
export function chartRows(c: ChartSpec): Record<string, string | number>[] {
  const order: (string | number)[] = []
  const rows = new Map<string | number, Record<string, string | number>>()
  c.series.forEach((s, i) => {
    for (const p of s.points) {
      if (!rows.has(p.x)) {
        order.push(p.x)
        rows.set(p.x, { x: p.x })
      }
      rows.get(p.x)![`s${i}`] = p.y
    }
  })
  return order.map((x) => rows.get(x)!)
}

/** The point behind a row's value, for its marker and its passages. */
export function pointAt(c: ChartSpec, seriesIndex: number, x: string | number): ChartPoint | undefined {
  return c.series[seriesIndex]?.points.find((p) => p.x === x)
}

/** The passage a click on a value opens: its first ref, else the first one
 *  it was computed from. */
export function pointPassage(p: ChartPoint): number | null {
  return p.refs[0] ?? p.derived_from?.[0] ?? null
}

/** The chart as CSV: the x column, then a column per series. */
export function chartCsv(c: ChartSpec): string {
  const esc = (v: string | number | undefined) => {
    const s = v === undefined ? '' : String(v)
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const head = [c.x_label || 'x', ...c.series.map((s) => s.name)].map(esc).join(',')
  const lines = chartRows(c).map((r) => [r.x, ...c.series.map((_, i) => r[`s${i}`])].map(esc).join(','))
  return [head, ...lines].join('\n') + '\n'
}

/** A file name from a chart's title. */
export function chartFileName(title: string, ext: 'png' | 'csv'): string {
  const base = title.normalize('NFKD').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').toLowerCase().slice(0, 60)
  return `${base || 'chart'}.${ext}`
}

/** What a chart proposal belongs to: the notebook, the selected sources
 *  (all of them when none are given), the pages fetched again and the
 *  notes. Candidates found for another key are stale: proposed from other
 *  material, they must not be sent with Create. */
export function proposalKey(notebookId: string, sourceIds: readonly string[] | undefined, instructions: string, urlRefresh: readonly string[] = []): string {
  return JSON.stringify([notebookId, sourceIds ? [...sourceIds].sort() : null, [...urlRefresh].sort(), instructions.trim().replace(/\s+/g, ' ')])
}
