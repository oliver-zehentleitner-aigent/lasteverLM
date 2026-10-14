import { ApiError } from '../api/client'
import { t } from '../i18n'

/** The delete button waits for the account's address, typed as it is
 *  shown (case and surrounding spaces aside). */
export function confirmsEmail(typed: string, email: string): boolean {
  return typed.trim().toLowerCase() === email.trim().toLowerCase() && email.trim() !== ''
}

/** What a failed delete says under the dialog: for a 502 the step that
 *  failed and its message (the user is then still there), otherwise the
 *  service's sentence, e.g. the 409 for one's own account. */
export function deleteFailure(err: unknown): string {
  if (err instanceof ApiError && err.status === 502 && err.body && typeof err.body === 'object') {
    const { step, message } = err.body as { step?: unknown; message?: unknown }
    if (typeof step === 'string' && step) {
      return t('adm.delUser.failedStep', { step, message: typeof message === 'string' && message ? message : '—' })
    }
  }
  return err instanceof Error ? err.message : String(err)
}
