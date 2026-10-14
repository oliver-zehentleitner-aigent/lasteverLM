import type { SourceStatus } from '../api/types'
import { t } from '../i18n'
import { pendingReason } from '../lib/pendingReason'

/** The line next to an unfinished source's badge saying why it is not
 *  moving: amber when an admin has to act (no exchange rate), muted for a
 *  retry or another note. Nothing when there is none. */
export function PendingReason({ status, error, className }: { status: SourceStatus; error: string | null; className?: string }) {
  const r = pendingReason(status, error)
  if (!r) return null
  return (
    <span className={[r.admin ? 'small pending-admin' : 'muted small', className].filter(Boolean).join(' ')} title={r.text}>
      {r.text}
    </span>
  )
}

/** A source's status as one short, compact badge for a one-line row: a
 *  failed source's error, why a waiting one is not moving, or what a long
 *  status means, all in its tooltip; amber only where an admin has to act. */
export function StatusBadge({ status, error }: { status: SourceStatus; error: string | null }) {
  const r = pendingReason(status, error)
  const title = status === 'failed' ? (error ?? t('status.failed')) : (r?.text ?? t(`status.${status}`))
  return (
    <span className={`badge ${status}${r?.admin ? ' pending-admin' : ''}`} title={title}>
      {t(`statusShort.${status}`)}
    </span>
  )
}
