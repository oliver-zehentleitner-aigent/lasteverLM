import { ApiError } from '../api/client'
import { t } from '../i18n'

/** What a refused starter copy means for the user: ingest's codes come as
 *  the `error` itself. "exists" asks to confirm a second copy; the rest is
 *  a sentence. Pure, so it is tested. */
export function starterCopyRefusal(err: unknown): { kind: 'exists' } | { kind: 'message'; text: string } {
  const body = err instanceof ApiError ? (err.body as { error?: unknown; retry_after?: unknown } | null) : null
  const code = typeof body?.error === 'string' ? body.error : null
  if (code === 'starter_exists') return { kind: 'exists' }
  if (code === 'starter_copy_too_soon') {
    const s = typeof body?.retry_after === 'number' ? body.retry_after : null
    return { kind: 'message', text: s === null ? t('help.starter.tooSoon') : t('help.starter.tooSoonIn', { minutes: Math.max(1, Math.ceil(s / 60)) }) }
  }
  if (code === 'no_starter') return { kind: 'message', text: t('help.starter.none') }
  return { kind: 'message', text: err instanceof Error ? err.message : String(err) }
}
