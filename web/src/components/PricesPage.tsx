import { useEffect, useState } from 'react'
import { account } from '../api/account'
import type { PublicPrices } from '../api/types'
import { t } from '../i18n'
import { actionLabel, formatPrice, groupPrices, typicalText, unitLabel } from '../lib/prices'

/** /prices: what each action costs today, for everyone, no login. One
 *  table per group (sources, chat, outputs, extras) with the price per
 *  unit, the typical range per action and the model; under it the
 *  exchange rate and the rules in plain words. End prices only: no
 *  margins, fees or costs are sent or shown. */
export function PricesPage() {
  const [prices, setPrices] = useState<PublicPrices | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    account.prices().then(setPrices, (e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  return (
    <main className="shared prices-page">
      <header className="topbar">
        <a href="/" className="brand">
          lasteverLM
        </a>
        <span className="muted small">{t('prices.label')}</span>
      </header>
      <div className="viewer-body">
        <h1 className="doc-title">{t('prices.title')}</h1>
        <p className="muted">{t('prices.intro', { days: prices?.window_days ?? 30 })}</p>
        {error && <p className="error">{error}</p>}
        {!prices && !error && <p className="muted">{t('common.loading')}</p>}
        {prices &&
          groupPrices(prices.actions).map(({ group, rows }) => (
            <section key={group} className="price-group">
              <h2>{t(`prices.group.${group}`)}</h2>
              <div className="table-scroll">
                <table className="price-table">
                  <thead>
                    <tr>
                      <th>{t('prices.col.what')}</th>
                      <th>{t('prices.col.perUnit')}</th>
                      <th>{t('prices.col.typical')}</th>
                      <th className="model">{t('prices.col.model')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.action}>
                        <td>{actionLabel(r.action)}</td>
                        {r.price_per_unit_cents === null ? (
                          <td className="muted" colSpan={2}>
                            {t('prices.noExperience')}
                          </td>
                        ) : (
                          <>
                            <td>
                              {formatPrice(r.price_per_unit_cents)} <span className="muted small">{unitLabel(r.unit)}</span>
                            </td>
                            <td>{typicalText(r) ?? <span className="muted">{t('prices.noExperience')}</span>}</td>
                          </>
                        )}
                        <td className="model muted small">{r.model ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        {prices && (
          <section className="price-rules">
            <p className="muted small">
              {prices.usd_per_eur === null
                ? t('prices.noRate')
                : prices.rate_source === 'ECB' && prices.rate_date
                  ? t('prices.rateEcb', { rate: prices.usd_per_eur, date: prices.rate_date })
                  : t('prices.rate', { rate: prices.usd_per_eur })}
            </p>
            <h2>{t('prices.rulesTitle')}</h2>
            <ul>
              <li>{t('prices.rule.addFree')}</li>
              <li>{t('prices.rule.processing')}</li>
              <li>{t('prices.rule.seeFirst')}</li>
              <li>{t('prices.rule.noExpiry')}</li>
            </ul>
          </section>
        )}
      </div>
    </main>
  )
}
