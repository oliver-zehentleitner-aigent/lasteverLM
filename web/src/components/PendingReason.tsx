import type { SourceStatus } from '../api/types'
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
