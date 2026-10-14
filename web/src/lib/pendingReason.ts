import type { SourceStatus } from '../api/types'
import { t } from '../i18n'

/** The text ingest and rag give while pricing has no exchange rate: the
 *  source waits, nothing was tried, and an admin has to act. */
export const NO_RATE_REASON = 'pricing has no exchange rate, ask an admin'

/** Why a source that has not finished is not moving, for the line next to
 *  its badge; null when there is nothing to say. The rate's text as it
 *  comes (it is no retry); another error while processing is a retry;
 *  one while waiting for credit as it comes. A failed source's error is
 *  shown as an error elsewhere. Pure, so it is tested. */
export function pendingReason(status: SourceStatus, error: string | null): { text: string; admin: boolean } | null {
  if (!error || (status !== 'processing' && status !== 'waiting_for_credit')) return null
  if (error === NO_RATE_REASON) return { text: error, admin: true }
  return { text: status === 'processing' ? t('sources.retrying', { error }) : error, admin: false }
}
