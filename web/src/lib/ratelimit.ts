import type { RateLimitRules, RateLimitUpdate } from '../api/types'

/** Core's bounds for the editable fields, inclusive; the server answers 422
 *  outside them, the form checks first so the message comes sooner. */
export const RATE_LIMIT_BOUNDS: Record<keyof RateLimitUpdate, [number, number]> = {
  per_minute: [1, 10000],
  block_minutes: [1, 1440],
  ban_after_strikes: [1, 100],
  strike_window_hours: [1, 720],
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** The rule as one readable paragraph, as the admin page shows it. */
export function describeRateLimit(r: RateLimitRules): string {
  return (
    `More than ${plural(r.per_minute, 'request', 'requests')} per minute from one IP: ` +
    `blocked for ${plural(r.block_minutes, 'minute', 'minutes')}, one strike. ` +
    `${plural(r.ban_after_strikes, 'strike', 'strikes')} within ${plural(r.strike_window_hours, 'hour', 'hours')}: ` +
    `banned until an admin lifts it, at most ${plural(r.ban_max_days, 'day', 'days')}.`
  )
}

/** The first field outside its bounds, as a sentence, or null. */
export function rateLimitError(u: RateLimitUpdate): string | null {
  for (const [field, [lo, hi]] of Object.entries(RATE_LIMIT_BOUNDS) as [keyof RateLimitUpdate, [number, number]][]) {
    const v = u[field]
    if (!Number.isInteger(v) || v < lo || v > hi) return `${field} must be between ${lo} and ${hi}`
  }
  return null
}
