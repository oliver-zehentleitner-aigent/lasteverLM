import type { OutputKind, PublicPriceRow, SourceKind } from '../api/types'
import { hasMessage, language, t } from '../i18n'
import { OUTPUT_FORMS, SOURCE_FORMS, formFor, sourceKindLabel } from './outputs'

/** The public price list's groups, in the page's order. Pure, so it is tested. */
export type PriceGroup = 'sources' | 'chat' | 'outputs' | 'extras'

// the judge once per level, low to high, then the rest
const EXTRAS_ORDER = ['judge:low', 'judge:medium', 'judge:high', 'judge', 'chart_propose', 'decision', 'summary', 'voice_sample']

export function priceGroup(action: string): PriceGroup {
  if (action.startsWith('source:')) return 'sources'
  if (action.startsWith('output:')) return 'outputs'
  if (action === 'chat_answer') return 'chat'
  return 'extras'
}

/** The rows by group, each group in the order the app shows its kinds
 *  (sources and outputs as in the wizard and the tiles); an action the web
 *  does not know yet goes last in its group rather than being dropped. */
export function groupPrices(rows: PublicPriceRow[]): { group: PriceGroup; rows: PublicPriceRow[] }[] {
  const order = (a: string): number => {
    // a way of reading a kind ("source:pdf:vision") right after the kind
    const way = /^source:([^:]+):/.exec(a)
    if (way) return SOURCE_FORMS.findIndex((f) => f.kind === way[1]) + 0.5
    const sourceIdx = SOURCE_FORMS.findIndex((f) => `source:${f.kind}` === a)
    const outputIdx = OUTPUT_FORMS.findIndex((f) => `output:${f.kind}` === a)
    const i = sourceIdx >= 0 ? sourceIdx : outputIdx >= 0 ? outputIdx : EXTRAS_ORDER.indexOf(a)
    return i >= 0 ? i : 1000
  }
  return (['sources', 'chat', 'outputs', 'extras'] as const)
    .map((group) => ({ group, rows: rows.filter((r) => priceGroup(r.action) === group).sort((a, b) => order(a.action) - order(b.action) || a.action.localeCompare(b.action)) }))
    .filter((g) => g.rows.length > 0)
}

/** "PDF", "Report", "Judge, medium"; the code itself for an action the web
 *  has no name for. */
export function actionLabel(action: string): string {
  const judge = /^judge:(low|medium|high)$/.exec(action)
  if (judge) return t('prices.action.judgeLevel', { level: t(`judge.level.${judge[1] as 'low' | 'medium' | 'high'}`).toLowerCase() })
  if (action === 'source:pdf') return `${sourceKindLabel('pdf')} (${t('capture.text')})`
  if (action === 'source:pdf:vision') return `${sourceKindLabel('pdf')} (${t('capture.vision')})`
  if (action.startsWith('source:')) return sourceKindLabel(action.slice(7) as SourceKind)
  if (action.startsWith('output:')) {
    const kind = action.slice(7) as OutputKind
    return OUTPUT_FORMS.some((f) => f.kind === kind) ? formFor(kind).label : kind
  }
  const key = `prices.action.${action}`
  return hasMessage(key) ? t(key) : action
}

/** "per question", "per minute of audio"; the key itself for a unit the web does not know. */
export function unitLabel(unit: string): string {
  const key = `prices.unit.${unit}`
  return hasMessage(key) ? t(key) : t('prices.unit.other', { unit })
}

/** A price as a user reads it: whole cents from 10 cents up, below that
 *  two significant digits (€0.0034, €0.035), so a fraction of a cent is
 *  neither shown as €0.00 nor with six decimals. */
export function formatPrice(cents: number): string {
  const value = cents / 100
  const opts: Intl.NumberFormatOptions =
    cents >= 10 || cents === 0
      ? { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 }
      : { style: 'currency', currency: 'EUR', maximumSignificantDigits: 2 }
  return value.toLocaleString(language(), opts)
}

/** "€0.02–€0.05, median €0.03"; null without enough actions. */
export function typicalText(row: PublicPriceRow): string | null {
  const tc = row.typical_cents
  if (!tc) return null
  return t('prices.typicalRange', { p25: formatPrice(tc.p25), p75: formatPrice(tc.p75), median: formatPrice(tc.median) })
}

/** The price cell: a range "€0.01–€0.05" when min and max differ as shown,
 *  else the one price; the per-source part ("+ €0.01 per source") and
 *  whether it is an estimate apart. `price` null: no price could be made. */
export function priceText(row: PublicPriceRow): { price: string | null; perSource: string | null; estimated: boolean } {
  const mid = row.price_per_unit_cents
  const min = row.price_min_cents
  const max = row.price_max_cents
  let price: string | null = null
  if (mid !== null) {
    price = min != null && max != null && formatPrice(min) !== formatPrice(max) ? t('prices.range', { min: formatPrice(min), max: formatPrice(max) }) : formatPrice(mid)
  }
  const perSource = row.per_source_cents ? t('prices.perSource', { price: formatPrice(row.per_source_cents) }) : null
  return { price, perSource, estimated: mid !== null && row.estimated === true }
}
