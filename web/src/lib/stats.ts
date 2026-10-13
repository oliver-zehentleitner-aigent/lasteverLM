import type { AccountStats, IngestStats, RagStats, SystemInfo } from '../api/types'
import { language, t, tn } from '../i18n'
import { adminPath } from './adminPages'
import { known } from './build'
import { formatCents } from './format'

/** One number of the overview's KPI row: a value, a one-word label and an
 *  optional muted detail. Never coloured; what needs action goes to the
 *  attention strip. */
export interface KpiTile {
  key: string
  label: string
  value: string
  detail?: string
}

const n = (v: number) => v.toLocaleString(language())
const DASH = '—'

/** The six KPI tiles. Each service's stats load on their own, so a
 *  missing one shows a dash instead of holding the row back. */
export function kpiTiles(a: AccountStats | null, i: IngestStats | null, r: RagStats | null): KpiTile[] {
  const docsTotal = r ? Object.values(r.outputs.by_status).reduce((x, y) => x + y, 0) : null
  const docsFailed = r?.outputs.by_status.failed ?? 0
  return [
    { key: 'users', label: t('kpi.users'), value: a ? n(a.users) : DASH },
    { key: 'logins', label: t('kpi.logins24h'), value: a ? n(a.logins_24h) : DASH },
    {
      key: 'cost',
      label: t('kpi.cost24h'),
      value: a ? formatCents(a.usage_cost_cents.last_24h) : DASH,
      detail: a ? t('kpi.costTotal', { value: formatCents(a.usage_cost_cents.total) }) : undefined,
    },
    { key: 'vouchers', label: t('kpi.openVouchers'), value: a ? n(a.vouchers.open) : DASH },
    {
      key: 'sources',
      label: t('kpi.sources'),
      value: i ? n(i.sources.ready) : DASH,
      detail: i && i.sources.failed > 0 ? t('kpi.failed', { n: n(i.sources.failed) }) : undefined,
    },
    {
      key: 'documents',
      label: t('kpi.documents'),
      value: docsTotal === null ? DASH : n(docsTotal),
      detail: docsFailed > 0 ? t('kpi.failed', { n: n(docsFailed) }) : undefined,
    },
  ]
}

/** One line of the attention strip: something an admin can act on, with
 *  the page where that happens. */
export interface AttentionItem {
  key: string
  text: string
  href: string
}

/** Only what has a page to act on: bans and blocks (Security), services
 *  down or without a reported version (System). Failed sources and
 *  documents have no admin page, so they stay a detail on their tiles. */
export function attentionItems(a: AccountStats | null, s: SystemInfo | null): AttentionItem[] {
  const items: AttentionItem[] = []
  if (a && a.bans_active > 0) items.push({ key: 'bans', text: tn('att.bans', a.bans_active), href: adminPath('security') })
  if (a && a.blocks_active > 0) items.push({ key: 'blocks', text: tn('att.blocks', a.blocks_active), href: adminPath('security') })
  for (const svc of s?.services ?? []) {
    if (!svc.healthy) items.push({ key: `down-${svc.name}`, text: t('att.down', { name: svc.name }), href: adminPath('system') })
  }
  const unversioned = (s?.services ?? []).filter((svc) => svc.healthy && !known(svc.version)).length
  if (unversioned > 0) items.push({ key: 'versions', text: tn('att.noVersion', unversioned), href: adminPath('system') })
  return items
}

/** The overview's meta line: build and how many services are healthy. */
export function systemMeta(s: SystemInfo): { build: string | null; health: string; dots: { name: string; healthy: boolean }[] } {
  const v = known(s.version)
  const c = known(s.commit)
  const build = [v && `v${v}`, c && c.slice(0, 7)].filter(Boolean).join(' · ') || null
  const ok = s.services.filter((x) => x.healthy).length
  const total = s.services.length
  const health = ok === total ? tn('meta.allHealthy', total) : t('meta.someHealthy', { ok, n: total })
  return { build, health, dots: s.services.map((x) => ({ name: x.name, healthy: x.healthy })) }
}
