import { Suspense, lazy, useCallback, useEffect, useState, type FormEvent, type MouseEvent } from 'react'
import { admin } from '../../api/admin'
import { ApiError } from '../../api/client'
import type { CostGroup, ExchangeRateStatus, FinanceCosts, FinanceInfra, FinanceProfit, FinanceRevenue, PricingRules, PricingView } from '../../api/types'
import { useAsync } from '../../hooks/useAsync'
import { useLoad } from '../../hooks/useLoad'
import { FINANCE_PAGES, financePageFromPath, financePath, type FinancePageId } from '../../lib/adminPages'
import { formatTime } from '../../lib/format'
import { rateLine } from '../../lib/exchangeRate'
import { charge, exactMoney, formatMoney, lastDays } from '../../lib/money'
import { Money } from '../Money'
import { t } from '../../i18n'
import { useCanWrite } from './canWrite'
import { Vouchers } from './Credits'
import { Section, Table } from './shared'

// recharts comes with it, as on the overview
const ProfitChart = lazy(() => import('./ProfitChart'))

type Range = { from: string; to: string }

/** Admin > Finance: costs, prices, revenue and profit, infrastructure and
 *  vouchers, each its own page under /admin/finance/, the date range
 *  shared by the pages that take one. Every amount is EUR (core converts at
 *  booking with the rate in the price rule); the measured USD cost of
 *  usage and USD infrastructure lines are shown beside it. */
export function FinancePage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const page: FinancePageId = financePageFromPath(window.location.pathname) ?? 'costs'
  const [range, setRange] = useState<Range>(() => lastDays(30))
  const go = (p: FinancePageId) => (e: MouseEvent) => {
    e.preventDefault()
    onNavigate(financePath(p))
  }
  const ranged = page === 'costs' || page === 'revenue' || page === 'infrastructure'
  return (
    <section className="finance">
      <nav className="kind-chips finance-nav" aria-label={t('admin.page.finance')}>
        {FINANCE_PAGES.map((p) => (
          <a key={p.id} href={financePath(p.id)} className={p.id === page ? 'preset active' : 'preset'} aria-current={p.id === page ? 'page' : undefined} onClick={go(p.id)}>
            {p.label}
          </a>
        ))}
      </nav>
      {ranged && <RangePicker range={range} onChange={setRange} />}
      {page === 'costs' && <CostsPage range={range} />}
      {page === 'prices' && <PricesPage />}
      {page === 'revenue' && <RevenuePage range={range} onPrices={() => onNavigate(financePath('prices'))} />}
      {page === 'infrastructure' && <InfraPage range={range} />}
      {page === 'vouchers' && <Vouchers />}
    </section>
  )
}

/** 7, 30 or 90 days up to today, or any two dates. */
function RangePicker({ range, onChange }: { range: Range; onChange: (r: Range) => void }) {
  return (
    <div className="range-picker">
      {[7, 30, 90].map((d) => {
        const r = lastDays(d)
        const active = r.from === range.from && r.to === range.to
        return (
          <button key={d} type="button" className={active ? 'preset active' : 'preset'} aria-pressed={active} onClick={() => onChange(r)}>
            {t('fin.days', { n: d })}
          </button>
        )
      })}
      <label>
        {t('fin.from')}
        <input type="date" value={range.from} max={range.to} onChange={(e) => e.target.value && onChange({ ...range, from: e.target.value })} />
      </label>
      <label>
        {t('fin.to')}
        <input type="date" value={range.to} min={range.from} onChange={(e) => e.target.value && onChange({ ...range, to: e.target.value })} />
      </label>
    </div>
  )
}

const usd = (c: number) => formatMoney(c, 'USD')
const eur = (c: number) => formatMoney(c, 'EUR')

/** Real cost and what was charged, per day, action, model, user or service. */
function CostsPage({ range }: { range: Range }) {
  const [group, setGroup] = useState<CostGroup>('day')
  const load = useCallback(() => admin.financeCosts(range.from, range.to, group), [range, group])
  const { data, error } = useLoad<FinanceCosts | null>(load, null)
  return (
    <Section title={t('fin.page.costs')}>
      <p className="muted small">{t('fin.eurNote')}</p>
      <label className="inline">
        {t('fin.groupBy')}
        <select value={group} onChange={(e) => setGroup(e.target.value as CostGroup)}>
          {(['day', 'action', 'model', 'user', 'service'] as const).map((g) => (
            <option key={g} value={g}>
              {t(`fin.group.${g}`)}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="error">{error}</p>}
      {data && (
        <>
          <p title={t('fin.costTotals', { cost: exactMoney(data.total_cost_cents), usd: exactMoney(data.total_cost_usd_cents, 'USD'), charge: exactMoney(data.total_charge_cents) })}>
            {t('fin.costTotals', { cost: eur(data.total_cost_cents), usd: usd(data.total_cost_usd_cents), charge: eur(data.total_charge_cents) })}
          </p>
          <Table
            head={[t(`fin.group.${group}`), t('fin.col.calls'), t('fin.col.actions'), t('fin.col.cost'), t('fin.col.costUsd'), t('fin.col.charge'), t('fin.col.margin')]}
            rows={data.rows.map((r) => [
              r.key,
              r.calls,
              r.actions,
              <Money key="cost_cents" cents={r.cost_cents} />,
              <Money key="cost_usd_cents" cents={r.cost_usd_cents} currency="USD" />,
              <Money key="charge_cents" cents={r.charge_cents} />,
              r.cost_cents > 0 ? `${Math.round(((r.charge_cents - r.cost_cents) / r.cost_cents) * 100)} %` : '—',
            ])}
          />
        </>
      )}
    </Section>
  )
}

/** The rate's line ("1 EUR = 1.1188 USD · ECB 2026-10-13 · checked 14:05"),
 *  amber when the ECB has not answered for three days, the last error when
 *  there is one, and the automatic | manual switch with Check now. */
function RateStatus({ rate, busy, onMode, onSync }: { rate: ExchangeRateStatus; busy: boolean; onMode: (mode: ExchangeRateStatus['mode']) => void; onSync: () => void }) {
  return (
    <div className="rate-status">
      <div className="row">
        <span className="presets rate-mode" role="radiogroup" aria-label={t('fin.rate.mode')}>
          {(['automatic', 'manual'] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={rate.mode === m} className={rate.mode === m ? 'preset active' : 'preset'} title={t(`fin.rate.${m}Title`)} disabled={busy} onClick={() => rate.mode !== m && onMode(m)}>
              {t(`fin.rate.${m}`)}
            </button>
          ))}
        </span>
        {rate.mode === 'automatic' && (
          <button type="button" className="secondary small" disabled={busy} onClick={onSync}>
            {t('fin.rate.checkNow')}
          </button>
        )}
      </div>
      <p className={rate.stale ? 'small rate-line stale' : 'muted small rate-line'} title={rate.stale ? t('fin.rate.stale') : undefined}>
        {rateLine(rate)}
      </p>
      {rate.stale && <p className="small stale">{t('fin.rate.stale')}</p>}
      {rate.last_error && <p className="error small">{t('fin.rate.error', { error: rate.last_error })}</p>}
    </div>
  )
}

const EMPTY_RULES: PricingRules = { usd_per_eur: 1, default_margin_pct: 0, actions: {} }

/** The price rule: a margin on every action's cost, overridden per action
 *  by a margin and/or a fixed fee; every change previews what the last 30
 *  days' actions would cost the user, before it is saved. The EUR/USD rate
 *  for infrastructure sits here too. */
function PricesPage() {
  const canWrite = useCanWrite()
  const [view, setView] = useState<PricingView | null>(null)
  const [draft, setDraft] = useState<PricingRules>(EMPTY_RULES)
  const [dirty, setDirty] = useState(false)
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => {
      const v = await admin.getPricing()
      setView(v)
      setDraft(v.rules)
    })
  }, [run])

  // a changed rule shows its effect a moment after typing stops
  useEffect(() => {
    if (!dirty) return
    const timer = window.setTimeout(() => {
      admin.previewPricing(draft).then((v) => setView((prev) => ({ ...v, rate: v.rate ?? prev?.rate })), () => {})
    }, 400)
    return () => window.clearTimeout(timer)
  }, [draft, dirty])

  const edit = (next: PricingRules) => {
    setDraft(next)
    setDirty(true)
  }
  const setAction = (action: string, patch: { margin_pct?: number | null; fixed_cents?: number | null }) => {
    const cur = { ...draft.actions[action] }
    for (const [k, v] of Object.entries(patch) as ['margin_pct' | 'fixed_cents', number | null][]) {
      if (v === null || Number.isNaN(v)) delete cur[k]
      else cur[k] = v
    }
    const actions = { ...draft.actions }
    if (Object.keys(cur).length === 0) delete actions[action]
    else actions[action] = cur
    edit({ ...draft, actions })
  }
  const num = (s: string) => (s.trim() === '' ? null : Number(s))

  async function save(e: FormEvent) {
    e.preventDefault()
    const v = await run(() => admin.savePricing(draft))
    if (v) {
      setView(v)
      setDraft(v.rules)
      setDirty(false)
    }
  }
  // the mode switch and Check now return the view with the new rate; the
  // rest of an unsaved draft stays
  async function rateCall(call: () => Promise<PricingView>) {
    const v = await run(call)
    if (v) {
      setView(v)
      setDraft((d) => ({ ...d, usd_per_eur: v.rules.usd_per_eur }))
    }
  }
  async function reset() {
    if (!confirm(t('fin.price.resetConfirm'))) return
    const v = await run(async () => {
      await admin.resetPricing()
      return admin.getPricing()
    })
    if (v) {
      setView(v)
      setDraft(v.rules)
      setDirty(false)
    }
  }

  return (
    <>
      <Section title={t('fin.page.prices')}>
        <p className="muted small">{t('fin.price.intro')}</p>
        {error && <p className="error">{error}</p>}
        {view && (
          <form onSubmit={save}>
            <fieldset className="plain" disabled={!canWrite} title={canWrite ? undefined : t('adm.readOnlyTitle')}>
              {view.rate && <RateStatus rate={view.rate} busy={busy} onMode={(mode) => void rateCall(() => admin.setRateMode(mode))} onSync={() => void rateCall(() => admin.syncRate())} />}
              <label className="inline">
                {t('fin.rate.label')}
                <input
                  type="number"
                  className="narrow"
                  min={0.1}
                  max={10}
                  step="0.0001"
                  required
                  // the ECB's rate is not typed over; manual makes it editable
                  readOnly={view.rate?.mode === 'automatic'}
                  value={draft.usd_per_eur}
                  onChange={(e) => edit({ ...draft, usd_per_eur: Number(e.target.value) })}
                />
              </label>
              <p className="muted small">{t('fin.rate.hint')}</p>
              <label className="inline">
                {t('fin.price.defaultMargin')}
                <input type="number" className="narrow" min={0} max={1000} step={1} value={draft.default_margin_pct} onChange={(e) => edit({ ...draft, default_margin_pct: Number(e.target.value) || 0 })} />
                %
              </label>
              <div className="table-scroll">
                <table className="pricing">
                  <thead>
                    <tr>
                      <th>{t('fin.col.action')}</th>
                      <th>{t('fin.col.count30')}</th>
                      <th>{t('fin.col.avgCost')}</th>
                      <th>{t('fin.col.marginPct')}</th>
                      <th>{t('fin.col.fixed')}</th>
                      <th>{t('fin.col.userPays')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.actions.map((a) => {
                      const p = view.preview.find((x) => x.action === a)
                      const rule = draft.actions[a] ?? {}
                      return (
                        <tr key={a}>
                          <td>
                            <code>{a}</code>
                          </td>
                          <td>{p?.actions ?? 0}</td>
                          <td>{p?.avg_cost_cents == null ? '—' : <Money cents={p.avg_cost_cents} />}</td>
                          <td>
                            <input type="number" className="narrow" min={0} max={1000} placeholder={String(draft.default_margin_pct)} value={rule.margin_pct ?? ''} aria-label={t('fin.price.marginOf', { action: a })} onChange={(e) => setAction(a, { margin_pct: num(e.target.value) })} />
                          </td>
                          <td>
                            <input type="number" className="narrow" min={0} max={100000} step="0.01" placeholder="0" value={rule.fixed_cents ?? ''} aria-label={t('fin.price.fixedOf', { action: a })} onChange={(e) => setAction(a, { fixed_cents: num(e.target.value) })} />
                          </td>
                          <td className="small">
                            {p?.avg_cost_cents == null || p.charge_cents == null
                              ? '—'
                              : t('fin.price.preview', { cost: eur(p.avg_cost_cents), charge: eur(p.charge_cents) })}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="muted small">{t('fin.price.formula', { example: eur(charge(100, draft.default_margin_pct, 0)) })}</p>
              <div className="row">
                <button type="button" className="secondary" disabled={busy} onClick={() => void reset()}>
                  {t('fin.price.reset')}
                </button>
                <button type="submit" disabled={busy || !dirty}>
                  {t('fin.price.save')}
                </button>
              </div>
            </fieldset>
          </form>
        )}
      </Section>
    </>
  )
}

/** What came in and what it cost: charged, vouchers paid and free,
 *  outstanding credit, and profit per month or day with a chart. */
function RevenuePage({ range, onPrices }: { range: Range; onPrices: () => void }) {
  const [group, setGroup] = useState<'month' | 'day'>('month')
  const loadRevenue = useCallback(() => admin.financeRevenue(range.from, range.to), [range])
  const loadProfit = useCallback(() => admin.financeProfit(range.from, range.to, group), [range, group])
  const { data: rev, error: revError } = useLoad<FinanceRevenue | null>(loadRevenue, null)
  const { data: profit, error: profitError } = useLoad<FinanceProfit | null>(loadProfit, null)
  const noRate = profit?.rows.some((r) => r.infra_cost_cents === null) ?? false
  const rateLink = (
    <a
      href={financePath('prices')}
      onClick={(e) => {
        e.preventDefault()
        onPrices()
      }}
    >
      {t('fin.setRate')}
    </a>
  )

  return (
    <>
      <Section title={t('fin.rev.title')}>
        {revError && <p className="error">{revError}</p>}
        {rev && (
          <div className="stat-grid finance-tiles">
            <Tile label={t('fin.rev.charged')} cents={rev.charged_cents} detail={t('fin.rev.demo', { value: eur(rev.demo_charged_cents) })} />
            <Tile label={t('fin.rev.paidIssued')} cents={rev.vouchers.issued_paid_cents} detail={t('fin.rev.redeemed', { value: eur(rev.vouchers.redeemed_paid_cents) })} />
            <Tile label={t('fin.rev.freeIssued')} cents={rev.vouchers.issued_free_cents} detail={t('fin.rev.redeemed', { value: eur(rev.vouchers.redeemed_free_cents) })} />
            <Tile label={t('fin.rev.outstanding')} cents={rev.outstanding_credit_cents} />
          </div>
        )}
        <p className="muted small">{t('fin.rev.note')}</p>
      </Section>
      <Section title={t('fin.profit.title')}>
        <label className="inline">
          {t('fin.groupBy')}
          <select value={group} onChange={(e) => setGroup(e.target.value as 'month' | 'day')}>
            <option value="month">{t('fin.group.month')}</option>
            <option value="day">{t('fin.group.day')}</option>
          </select>
        </label>
        {profitError && <p className="error">{profitError}</p>}
        {noRate && <p className="notice small">{t('fin.profit.noRate')} {rateLink}</p>}
        {profit && profit.rows.length > 0 && (
          <Suspense fallback={<p className="muted small">{t('common.loading')}</p>}>
            <ProfitChart rows={profit.rows} />
          </Suspense>
        )}
        {profit && (
          <Table
            head={[t(`fin.group.${group}`), t('fin.col.charged'), t('fin.col.modelCost'), t('fin.col.infra'), t('fin.col.profit'), t('fin.col.demo')]}
            rows={[...profit.rows, ...(profit.total ? [{ ...profit.total, period: t('fin.total') }] : [])].map((r) => [
              r.period,
              <Money key="charged_cents" cents={r.charged_cents} />,
              <Money key="model_cost_cents" cents={r.model_cost_cents} />,
              r.infra_cost_cents === null ? <span key="infra" className="muted">{t('fin.needsRate')}</span> : <Money key="infra_cost_cents" cents={r.infra_cost_cents} />,
              r.profit_cents === null ? <span key="profit" className="muted">{t('fin.needsRate')}</span> : <strong key="profit" className={r.profit_cents < 0 ? 'loss' : undefined}><Money cents={r.profit_cents} /></strong>,
              t('fin.demoCell', { charged: eur(r.demo_charged_cents), cost: eur(r.demo_cost_cents) }),
            ])}
          />
        )}
      </Section>
    </>
  )
}

/** A finance tile: the amount by the one rule, its exact value as tooltip. */
function Tile({ label, cents, detail }: { label: string; cents: number; detail?: string }) {
  return (
    <div className="stat">
      <span className="stat-value">
        <Money cents={cents} />
      </span>
      <span className="muted small">{label}</span>
      {detail && <span className="muted small">{detail}</span>}
    </div>
  )
}

/** Infrastructure: Vultr's charges fetched daily (or how to connect it),
 *  and lines entered by hand, which can be deleted again. */
function InfraPage({ range }: { range: Range }) {
  const canWrite = useCanWrite()
  const load = useCallback(() => admin.financeInfra(range.from, range.to), [range])
  const { data, setData, error } = useLoad<FinanceInfra | null>(load, null)
  const { busy, error: actionError, run } = useAsync()
  const [entry, setEntry] = useState({ date: range.to, item: '', amount: '', currency: 'EUR' as 'EUR' | 'USD' })

  const failure = (err: unknown) => {
    if (err instanceof ApiError && err.code === 'vultr_not_connected') return t('fin.infra.notConnectedError')
    if (err instanceof ApiError && err.code === 'not_manual') return t('fin.infra.notManual')
    return err instanceof Error ? err.message : String(err)
  }

  async function sync() {
    const r = await run(async () => {
      try {
        return await admin.syncInfra()
      } catch (err) {
        throw new Error(failure(err))
      }
    })
    if (r) setData(r)
  }
  async function add(e: FormEvent) {
    e.preventDefault()
    const cents = Math.round(Number(entry.amount.replace(',', '.')) * 100)
    if (!entry.item.trim() || !Number.isFinite(cents) || cents < 0) return
    const ok = await run(() => admin.addInfra({ date: entry.date, item: entry.item.trim(), amount_cents: cents, currency: entry.currency }).then(() => true))
    if (ok) {
      setEntry({ ...entry, item: '', amount: '' })
      setData(await admin.financeInfra(range.from, range.to))
    }
  }
  async function remove(id: string, item: string) {
    if (!confirm(t('fin.infra.deleteConfirm', { item }))) return
    const ok = await run(async () => {
      try {
        await admin.deleteInfra(id)
        return true
      } catch (err) {
        throw new Error(failure(err))
      }
    })
    if (ok && data) setData({ ...data, entries: data.entries.filter((x) => x.id !== id) })
  }

  return (
    <Section title={t('fin.page.infrastructure')}>
      {(error ?? actionError) && <p className="error">{error ?? actionError}</p>}
      {data && (
        <>
          {data.configured ? (
            <div className="infra-status small">
              <p>
                {/* "connected" only once a sync has worked and the last one did not fail */}
                {data.last_success_at && !data.last_error
                  ? t('fin.infra.connected', { at: formatTime(data.last_success_at) })
                  : t('fin.infra.keySet', { at: data.last_success_at ? formatTime(data.last_success_at) : t('time.never') })}
                {data.last_attempt_at && data.last_attempt_at !== data.last_success_at && <span className="muted"> · {t('fin.infra.lastAttempt', { at: formatTime(data.last_attempt_at) })}</span>}{' '}
                {canWrite && (
                  <button type="button" className="link small" disabled={busy} onClick={() => void sync()}>
                    {t('fin.infra.sync')}
                  </button>
                )}
              </p>
              {data.last_error && <p className="error">{t('fin.infra.syncFailed', { error: data.last_error })}</p>}
            </div>
          ) : (
            <div className="notice small">
              <strong>{t('fin.infra.notConnected')}</strong>
              <p>{t('fin.infra.howTo')}</p>
            </div>
          )}
          <p>
            {data.total_eur_cents === null
              ? t('fin.infra.totalsByCurrency', { eur: eur(data.totals_by_currency.EUR ?? 0), usd: usd(data.totals_by_currency.USD ?? 0) })
              : t('fin.infra.total', { value: eur(data.total_eur_cents) })}
          </p>
          <Table
            head={[t('fin.col.date'), t('fin.col.item'), t('fin.col.source'), t('fin.col.amount'), t('fin.col.inEur'), '']}
            rows={data.entries.map((x) => [
              x.date,
              x.item,
              t(`fin.source.${x.source}`),
              <Money key="amount_cents" cents={x.amount_cents} currency={x.currency} />,
              x.amount_eur_cents === null ? <span key="eur" className="muted">{t('fin.needsRate')}</span> : <Money key="amount_eur_cents" cents={x.amount_eur_cents} />,
              x.source === 'manual' && canWrite ? (
                <button key="del" type="button" className="link danger" disabled={busy} onClick={() => void remove(x.id, x.item)}>
                  {t('common.delete')}
                </button>
              ) : (
                ''
              ),
            ])}
          />
          {canWrite && (
            <form className="row infra-add" onSubmit={add}>
              <label>
                {t('fin.col.date')}
                <input type="date" value={entry.date} onChange={(e) => setEntry({ ...entry, date: e.target.value })} />
              </label>
              <label className="grow">
                {t('fin.col.item')}
                <input maxLength={200} value={entry.item} placeholder={t('fin.infra.itemPlaceholder')} onChange={(e) => setEntry({ ...entry, item: e.target.value })} />
              </label>
              <label>
                {t('fin.col.amount')}
                <input inputMode="decimal" className="narrow" value={entry.amount} placeholder="12.50" onChange={(e) => setEntry({ ...entry, amount: e.target.value })} />
              </label>
              <label>
                {t('fin.col.currency')}
                <select value={entry.currency} onChange={(e) => setEntry({ ...entry, currency: e.target.value as 'EUR' | 'USD' })}>
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                </select>
              </label>
              <button type="submit" disabled={busy || !entry.item.trim() || !entry.amount.trim()}>
                {t('fin.infra.add')}
              </button>
            </form>
          )}
        </>
      )}
    </Section>
  )
}
