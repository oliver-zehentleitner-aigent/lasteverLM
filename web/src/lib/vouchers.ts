import { ApiError } from '../api/client'
import { t } from '../i18n'

/** rag-independent rules for showing and mailing voucher codes. */

export const MESSAGE_MAX = 1000

/** What a failed show or send says, by the account service's code; any
 *  other failure keeps the service's own sentence. A failed mail keeps
 *  the SMTP server's message after ours. */
export function voucherError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case 'not_recoverable':
        return t('vch.notRecoverable')
      case 'already_redeemed':
        return t('vch.err.redeemed')
      case 'too_many_mails':
        return t('vch.err.quota')
      case 'smtp_not_configured':
        return t('vch.err.noSmtp')
      case 'mail_failed':
        return t('vch.err.mail', { detail: err.message })
    }
  }
  return err instanceof Error ? err.message : String(err)
}

/** Enough of an address to send to: one @ with something on both sides
 *  and a dot in the domain; the service checks the rest. */
export function plausibleEmail(s: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim())
}
