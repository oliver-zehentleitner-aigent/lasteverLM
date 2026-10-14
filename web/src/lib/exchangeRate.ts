import type { ExchangeRateStatus } from '../api/types'
import { language, t } from '../i18n'

/** A check's time: the clock alone today, else the date with it. */
export function checkedAt(iso: string, now: Date = new Date()): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const time = d.toLocaleTimeString(language(), { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  return d.toDateString() === now.toDateString() ? time : `${d.toLocaleDateString(language())} ${time}`
}

/** "1 EUR = 1.1188 USD · ECB 2026-10-13 · checked 14:05": the rate, where
 *  it comes from (the ECB day, set by hand, or the starting value) and,
 *  in automatic mode, the last check. Pure, so it is tested. */
export function rateLine(r: ExchangeRateStatus, now: Date = new Date()): string {
  const parts = [r.usd_per_eur == null ? t('fin.rate.none') : t('fin.rate.value', { rate: r.usd_per_eur })]
  if (r.source === 'ECB') parts.push(r.rate_date ? t('fin.rate.ecb', { date: r.rate_date }) : 'ECB')
  else parts.push(t(r.source === 'manual' ? 'fin.rate.manualSource' : 'fin.rate.seed'))
  if (r.mode === 'automatic' && r.last_checked) parts.push(t('fin.rate.checked', { at: checkedAt(r.last_checked, now) }))
  return parts.join(' · ')
}
