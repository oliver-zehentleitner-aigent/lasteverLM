import type { EstimateState } from '../hooks/useEstimate'
import { t } from '../i18n'
import { priceLabel } from '../lib/estimate'

/** The estimated charge of what a button starts, next to the button.
 *  Nothing while it loads; "price unavailable" with the error in the
 *  tooltip when the estimate failed. Reading unread sources and re-reading
 *  web pages follow as their own lines ("+ Read a.pdf ≈ €0.03"), not added
 *  in: ingest bills them apart. */
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
  // reading unread sources and re-reading pages: billed apart by ingest, one line each, not in the total
  const separate = state.estimate.separate ?? []
  return (
    <span className="price-tag muted small" title={t('price.title')}>
      {priceLabel(state.estimate)}
      {suffix && ` ${suffix}`}
      {separate.map((x) => (
        <span key={`${x.library_id}:${x.label}`} className="price-separate" title={x.basis ?? undefined}>
          {t('price.separateLine', { label: x.label, price: priceLabel({ charge_cents_min: x.min, charge_cents_max: x.max }) })}
        </span>
      ))}
    </span>
  )
}
