import type { AccountStats, IngestStats, OutputKind, RagStats } from '../api/types'
import { formatBytes, formatCents } from './format'
import { formFor } from './outputs'

/** One number on the admin overview. `alert` marks a value that needs a
 *  look (failures, bans); `detail` is a short breakdown under it. */
export interface StatTile {
  label: string
  value: string
  detail?: string
  alert?: boolean
}

const n = (v: number) => v.toLocaleString()

export function accountTiles(s: AccountStats): StatTile[] {
  return [
    { label: 'Users', value: n(s.users) },
    { label: 'Logins, 24 h', value: n(s.logins_24h) },
    {
      label: 'Vouchers open',
      value: n(s.vouchers.open),
      detail: `${n(s.vouchers.issued)} issued · ${n(s.vouchers.redeemed)} redeemed`,
    },
    { label: 'Credit granted', value: formatCents(s.credits_granted_cents) },
    {
      label: 'Usage cost',
      value: formatCents(s.usage_cost_cents.total),
      detail: `${formatCents(s.usage_cost_cents.last_24h)} in 24 h`,
    },
    { label: 'Blocks active', value: n(s.blocks_active), alert: s.blocks_active > 0 },
    { label: 'Bans active', value: n(s.bans_active), alert: s.bans_active > 0 },
  ]
}

export function ingestTiles(s: IngestStats): StatTile[] {
  return [
    {
      label: 'Sources ready',
      value: n(s.sources.ready),
      detail: `${n(s.sources.processing)} processing`,
    },
    { label: 'Sources failed', value: n(s.sources.failed), alert: s.sources.failed > 0 },
    {
      label: 'Ingest jobs pending',
      value: n(s.jobs.pending),
      detail: `${n(s.jobs.running)} running`,
    },
    { label: 'Chunks', value: n(s.chunks) },
    { label: 'Stored sources', value: formatBytes(s.source_bytes) },
  ]
}

export function ragTiles(s: RagStats): StatTile[] {
  const total = Object.values(s.outputs.by_status).reduce((a, b) => a + b, 0)
  const kinds = (Object.entries(s.outputs.by_kind) as [OutputKind, number][])
    .filter(([, count]) => count > 0)
    .map(([kind, count]) => `${formFor(kind).label} ${n(count)}`)
    .join(' · ')
  return [
    { label: 'Notebooks', value: n(s.notebooks.total) },
    {
      label: 'Chat messages',
      value: n(s.messages.total),
      detail: `${n(s.messages.last_24h)} in 24 h`,
    },
    { label: 'Documents', value: n(total), detail: kinds || undefined },
    { label: 'Documents failed', value: n(s.outputs.by_status.failed), alert: s.outputs.by_status.failed > 0 },
    {
      label: 'Document jobs pending',
      value: n(s.jobs.pending),
      detail: `${n(s.jobs.running)} running`,
    },
    { label: 'Shared documents', value: n(s.shared.outputs) },
  ]
}
