import { t } from '../i18n'

/** Marks an entry copied from the starter notebook every new account gets.
 *  `demo` is ingest's name for the flag before it became `starter`. */
export function StarterBadge({ item }: { item: { starter?: boolean; demo?: boolean } }) {
  if (!item.starter && !item.demo) return null
  return (
    <span className="badge starter" title={t('starter.badgeTitle')}>
      {t('starter.badge')}
    </span>
  )
}
