import { t } from '../i18n'
import { formatCents } from './format'

/** What rag's estimate is asked for: an output by its kind and options, or
 *  another action. */
export type EstimateRequest = (
  | { kind: string; options?: Record<string, unknown> }
  | { action: 'chat_answer' | 'chart_propose' | 'table_propose' | 'infographic_propose' | 'voice_sample' | 'judge'; options?: Record<string, unknown> }
) & {
  /** with the notebook, the answer lists reading its unread sources (and re-reading pages) apart */
  notebook_id?: string
  source_ids?: string[]
  url_refresh?: string[]
}

/** rag's answer; the charge is what the user pays, in euro cents like
 *  their credit, to a hundredth of a cent and rounded outwards. */
export interface Estimate {
  action: string
  charge_cents_min: number
  charge_cents_max: number
  /** billed apart by ingest, not in the charge: reading an unread source, re-reading a page */
  separate?: { library_id: string; label: string; basis?: string | null; min: number; max: number }[]
  /** an output's full price at each verification level, whatever the options sent */
  levels?: Partial<Record<string, { min: number; max: number }>>
  /** selected sources that cannot be read; with any, the action would be refused (409) */
  blocked?: { library_id: string; name: string; reason: string }[]
}

/** The charge as a user reads it, in whole cents and still rounded
 *  outwards so the range holds: "≈ €0.03–€0.09", "≈ €0.05" when both ends
 *  meet, "up to €0.01" when the low end is under a cent. Pure, so it is
 *  tested. */
export function priceLabel(e: Pick<Estimate, 'charge_cents_min' | 'charge_cents_max'>): string {
  const min = Math.floor(e.charge_cents_min)
  const max = Math.max(Math.ceil(e.charge_cents_max), min)
  if (min === max) return t('price.about', { price: formatCents(min) })
  if (min === 0) return t('price.upTo', { price: formatCents(max) })
  return t('price.range', { min: formatCents(min), max: formatCents(max) })
}

/** The same request gives the same key, whatever the order of its fields. */
export function estimateKey(req: EstimateRequest): string {
  return JSON.stringify(req, (_k, v: unknown) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)))
      : v,
  )
}
