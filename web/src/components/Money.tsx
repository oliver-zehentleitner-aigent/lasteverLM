import { exactMoney, formatMoney } from '../lib/money'

/** An amount by the one rule (`formatMoney`), the exact value in its tooltip. */
export function Money({ cents, currency = 'EUR' }: { cents: number; currency?: 'EUR' | 'USD' }) {
  return <span title={exactMoney(cents, currency)}>{formatMoney(cents, currency)}</span>
}
