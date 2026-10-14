import { useEffect, useState } from 'react'
import { ingest } from '../api/ingest'
import type { Source } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { t } from '../i18n'
import { priceLabel } from '../lib/estimate'

/** "As read" for a source that is not read yet: there is no text to
 *  show. It says when it is read, with "read now" and its price (from
 *  ingest's estimate, asked once the view opens; asking is free). */
export function SourceUnread({ source, onRead }: { source: Source; onRead: () => void }) {
  const lib = source.library_id ?? source.id
  const [price, setPrice] = useState<{ label: string; basis: string | null } | null>(null)
  const { busy, error, run } = useAsync()

  useEffect(() => {
    let live = true
    ingest.readEstimate([lib]).then(
      (r) => {
        const item = r.items.find((x) => x.library_id === lib) ?? r.items[0]
        if (live && item) setPrice({ label: priceLabel({ charge_cents_min: item.charge_cents_min, charge_cents_max: item.charge_cents_max }), basis: item.basis ?? null })
      },
      () => {
        // without a price the button still reads it; the estimate's failure is no reason to block
      },
    )
    return () => {
      live = false
    }
  }, [lib])

  async function readNow() {
    const ok = await run(() => ingest.processSources([lib]).then(() => true))
    if (ok) onRead()
  }

  return (
    <div className="source-unread">
      <p className="muted">{t('srcView.notRead')}</p>
      <p>
        <button type="button" className="secondary small" disabled={busy} onClick={() => void readNow()}>
          {t('sources.readNow')}
        </button>{' '}
        {price && (
          <span className="muted small" title={price.basis ?? undefined}>
            {price.label}
            {price.basis && ` · ${price.basis}`}
          </span>
        )}
      </p>
      {error && <p className="error small">{error}</p>}
    </div>
  )
}
