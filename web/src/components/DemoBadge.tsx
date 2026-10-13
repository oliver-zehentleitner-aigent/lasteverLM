import { t } from '../i18n'

/** Marks one of the example sources a new account starts with. */
export function DemoBadge({ demo }: { demo?: boolean }) {
  if (!demo) return null
  return (
    <span className="badge demo" title={t('demo.badgeTitle')}>
      {t('demo.badge')}
    </span>
  )
}
