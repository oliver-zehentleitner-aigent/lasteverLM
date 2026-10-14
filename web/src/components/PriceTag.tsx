import type { EstimateState } from '../hooks/useEstimate'
import { t } from '../i18n'
import { priceLabel } from '../lib/estimate'

/** The estimated charge of what a button starts, next to the button.
 *  Nothing while it loads; "price unavailable" with the error in the
 *  tooltip when the estimate failed. */
export function PriceTag({ state, suffix }: { state: EstimateState; suffix?: string }) {
  if (!state) return null
  if ('noRate' in state)
    return (
      <span className="price-tag error small" title={t('price.noRateTitle')}>
        {t('price.noRate')}
      </span>
    )
  if ('failed' in state)
    return (
      <span className="price-tag muted small" title={t('price.failedTitle', { error: state.failed })}>
        {t('price.failed')}
      </span>
    )
  return (
    <span className="price-tag muted small" title={t('price.title')}>
      {priceLabel(state.estimate)}
      {suffix && ` ${suffix}`}
    </span>
  )
}
