import type { AccountStats, IngestStats, OutputKind, RagStats } from '../api/types'
import { language, t } from '../i18n'
import { adminPath } from './adminPages'
import { formatBytes, formatCents } from './format'
import { formFor } from './outputs'

/** One number on the admin overview. `alert` marks a value that needs a
 *  look (failures, bans); `detail` is a short breakdown under it. */
export interface StatTile {
  label: string
  value: string
  detail?: string
  alert?: boolean
  /** the admin page that explains the number, e.g. who got the credit */
  href?: string
}

const n = (v: number) => v.toLocaleString(language())

export function accountTiles(s: AccountStats): StatTile[] {
  return [
    { label: t('stat.users'), value: n(s.users) },
    { label: t('stat.logins24h'), value: n(s.logins_24h) },
    {
      label: t('stat.vouchersOpen'),
      value: n(s.vouchers.open),
      detail: t('stat.vouchersDetail', { issued: n(s.vouchers.issued), redeemed: n(s.vouchers.redeemed) }),
      href: adminPath('credits'),
    },
    { label: t('stat.creditGranted'), value: formatCents(s.credits_granted_cents), href: adminPath('users') },
    {
      label: t('stat.usageCost'),
      value: formatCents(s.usage_cost_cents.total),
      detail: t('stat.in24h', { value: formatCents(s.usage_cost_cents.last_24h) }),
    },
    { label: t('stat.blocksActive'), value: n(s.blocks_active), alert: s.blocks_active > 0 },
    { label: t('stat.bansActive'), value: n(s.bans_active), alert: s.bans_active > 0 },
  ]
}

export function ingestTiles(s: IngestStats): StatTile[] {
  return [
    {
      label: t('stat.sourcesReady'),
      value: n(s.sources.ready),
      detail: t('stat.processing', { n: n(s.sources.processing) }),
    },
    { label: t('stat.sourcesFailed'), value: n(s.sources.failed), alert: s.sources.failed > 0 },
    {
      label: t('stat.ingestPending'),
      value: n(s.jobs.pending),
      detail: t('stat.running', { n: n(s.jobs.running) }),
    },
    { label: t('stat.chunks'), value: n(s.chunks) },
    { label: t('stat.storedSources'), value: formatBytes(s.source_bytes) },
  ]
}

export function ragTiles(s: RagStats): StatTile[] {
  const total = Object.values(s.outputs.by_status).reduce((a, b) => a + b, 0)
  const kinds = (Object.entries(s.outputs.by_kind) as [OutputKind, number][])
    .filter(([, count]) => count > 0)
    .map(([kind, count]) => `${formFor(kind).label} ${n(count)}`)
    .join(' · ')
  return [
    { label: t('stat.notebooks'), value: n(s.notebooks.total) },
    {
      label: t('stat.chatMessages'),
      value: n(s.messages.total),
      detail: t('stat.in24h', { value: n(s.messages.last_24h) }),
    },
    { label: t('stat.documents'), value: n(total), detail: kinds || undefined },
    { label: t('stat.documentsFailed'), value: n(s.outputs.by_status.failed), alert: s.outputs.by_status.failed > 0 },
    {
      label: t('stat.documentPending'),
      value: n(s.jobs.pending),
      detail: t('stat.running', { n: n(s.jobs.running) }),
    },
    { label: t('stat.shared'), value: n(s.shared.outputs) },
  ]
}
