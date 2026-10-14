import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { account } from '../api/account'
import type { MyCredit } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useMe } from '../hooks/useMe'
import { t } from '../i18n'
import { creditLine } from '../lib/credit'
import { formatCents, formatTime } from '../lib/format'
import { writeLastNotebook, writeOpenOutput } from '../lib/lastNotebook'
import { lastDays } from '../lib/money'
import { actionLabel, formatPrice } from '../lib/prices'

const RANGES = [7, 30, 90] as const

/** /credits: the user's own credit. The balance with what was credited and
 *  spent in the range, a voucher field; then the spending per day as small
 *  bars and per action as a table; then every entry, linked to its
 *  notebook or output while that exists. End prices only, no costs. */
export function CreditsPage({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { me, setMe } = useMe()
  const [days, setDays] = useState<(typeof RANGES)[number]>(30)
  const [data, setData] = useState<MyCredit | null>(null)
  const { busy, error, run } = useAsync()
  const redeem = useAsync()
  const [code, setCode] = useState('')
  const [redeemed, setRedeemed] = useState(false)

  const load = useCallback(() => {
    const r = lastDays(days)
    void run(async () => setData(await account.credit(r.from, r.to)))
  }, [days, run])
  useEffect(load, [load])

  async function more() {
    if (!data) return
    const next = await run(() => account.credit(data.from, data.to, data.entries.length))
    if (next) setData({ ...next, entries: [...data.entries, ...next.entries] })
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setRedeemed(false)
    const user = await redeem.run(() => account.redeemVoucher(code.trim()))
    if (user) {
      setMe(user)
      setCode('')
      setRedeemed(true)
      load()
    }
  }

  function open(target: { notebookId: string; outputId?: string }) {
    writeLastNotebook(target.notebookId)
    if (target.outputId) writeOpenOutput(target.outputId)
    onNavigate('/')
  }

  const balance = data?.balance_cents ?? me?.balance_cents ?? null
  const maxDay = Math.max(1, ...(data?.by_day.map((d) => d.charged_cents) ?? [0]))
  return (
    <main className="credits">
      <h1>{t('credit.title')}</h1>
      <section className="card credit-head">
        <div>
          <span className="muted small">{t('credit.balance')}</span>
          <strong className="credit-balance">{balance === null ? '—' : formatCents(balance)}</strong>
          {data && (
            <span className="muted small">
              {t('credit.granted', { value: formatCents(data.granted_cents) })} · {t('credit.spent', { value: formatPrice(data.spent_cents) })} {t('credit.inRange')}
            </span>
          )}
        </div>
        <form className="row credit-redeem" onSubmit={submit}>
          <label>
            {t('credit.redeem')}
            <input value={code} placeholder={t('credit.redeemCode')} onChange={(e) => setCode(e.target.value)} autoComplete="off" />
          </label>
          <button type="submit" disabled={redeem.busy || !code.trim()}>
            {t('credit.redeem')}
          </button>
        </form>
        {redeem.error && <p className="error small">{redeem.error}</p>}
        {redeemed && <p className="muted small">{t('credit.redeemed')}</p>}
        <a
          href="/prices"
          className="small"
          onClick={(e) => {
            e.preventDefault()
            onNavigate('/prices')
          }}
        >
          {t('credit.priceList')}
        </a>
      </section>

      <section className="card">
        <div className="credit-spending-head">
          <h2>{t('credit.spending')}</h2>
          <span className="presets credit-range" role="radiogroup" aria-label={t('credit.spending')}>
            {RANGES.map((d) => (
              <button key={d} type="button" role="radio" aria-checked={days === d} className={days === d ? 'preset active' : 'preset'} onClick={() => setDays(d)}>
                {t('credit.days', { n: d })}
              </button>
            ))}
          </span>
        </div>
        {error && <p className="error">{error}</p>}
        {data && data.by_day.length > 0 && (
          <div className="credit-bars" role="img" aria-label={t('credit.spending')}>
            {data.by_day.map((d) => (
              <span
                key={d.day}
                className="credit-bar"
                style={{ height: `${Math.round((d.charged_cents / maxDay) * 100)}%` }}
                title={t('credit.dayTitle', { day: d.day, spent: formatPrice(d.charged_cents), credited: formatCents(d.credited_cents) })}
              />
            ))}
          </div>
        )}
        {data && data.by_action.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('credit.col.what')}</th>
                  <th>{t('credit.col.count')}</th>
                  <th>{t('credit.col.total')}</th>
                </tr>
              </thead>
              <tbody>
                {data.by_action.map((a) => (
                  <tr key={a.label_key ?? a.action}>
                    <td>{actionLabel(a.label_key ?? a.action)}</td>
                    <td>{a.count}</td>
                    <td>{formatPrice(a.charged_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>{t('credit.entries')}</h2>
        {data && data.entries.length === 0 && <p className="muted">{t('credit.none')}</p>}
        {data && data.entries.length > 0 && (
          <div className="table-scroll">
            <table className="credit-entries">
              <thead>
                <tr>
                  <th>{t('credit.col.date')}</th>
                  <th>{t('credit.col.what')}</th>
                  <th>{t('credit.col.amount')}</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e, i) => {
                  const line = creditLine(e)
                  return (
                    <tr key={`${e.at}-${i}`}>
                      <td className="muted small">{formatTime(e.at)}</td>
                      <td>
                        {line.open ? (
                          <a
                            href="/"
                            onClick={(ev) => {
                              ev.preventDefault()
                              open(line.open!)
                            }}
                          >
                            {line.text}
                          </a>
                        ) : (
                          line.text
                        )}
                      </td>
                      <td className={e.amount_cents < 0 ? 'amount minus' : 'amount plus'}>
                        {e.amount_cents < 0 ? `−${formatPrice(-e.amount_cents)}` : `+${formatCents(e.amount_cents)}`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {data && data.entries.length < data.total_entries && (
          <button type="button" className="secondary small" disabled={busy} onClick={() => void more()}>
            {t('credit.more')}
          </button>
        )}
      </section>
    </main>
  )
}
