import type { RateLimitRules, RateLimitUpdate } from '../api/types'
import { t, tn } from '../i18n'

/** Core's bounds for the editable fields, inclusive; the server answers 422
 *  outside them, the form checks first so the message comes sooner. */
export const RATE_LIMIT_BOUNDS: Record<keyof RateLimitUpdate, [number, number]> = {
  per_minute: [1, 10000],
  block_minutes: [1, 1440],
  ban_after_strikes: [1, 100],
  strike_window_hours: [1, 720],
}

/** The rule as one readable paragraph, as the admin page shows it. */
export function describeRateLimit(r: RateLimitRules): string {
  return t('rl.sentence', {
    requests: tn('rl.requests', r.per_minute),
    minutes: tn('rl.minutes', r.block_minutes),
    strikes: tn('rl.strikes', r.ban_after_strikes),
    hours: tn('rl.hours', r.strike_window_hours),
    days: tn('rl.days', r.ban_max_days),
  })
}

/** The first field outside its bounds, as a sentence, or null. */
export function rateLimitError(u: RateLimitUpdate): string | null {
  for (const [field, [lo, hi]] of Object.entries(RATE_LIMIT_BOUNDS) as [keyof RateLimitUpdate, [number, number]][]) {
    const v = u[field]
    if (!Number.isInteger(v) || v < lo || v > hi) return t('rl.bounds', { field, lo, hi })
  }
  return null
}
