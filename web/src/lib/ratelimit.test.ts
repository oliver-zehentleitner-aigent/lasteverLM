import { describe, expect, it } from 'vitest'
import { describeRateLimit, rateLimitError } from './ratelimit'

const rules = { per_minute: 120, block_minutes: 15, ban_after_strikes: 3, strike_window_hours: 24, ban_max_days: 90, retention_days: 30 }

describe('describeRateLimit', () => {
  it('renders the rule as a sentence', () => {
    expect(describeRateLimit(rules)).toBe(
      'More than 120 requests per minute from one IP: blocked for 15 minutes, one strike. ' +
        '3 strikes within 24 hours: banned until an admin lifts it, at most 90 days.',
    )
  })

  it('uses the singular for one', () => {
    expect(describeRateLimit({ ...rules, block_minutes: 1, ban_after_strikes: 1, strike_window_hours: 1 })).toContain(
      'blocked for 1 minute, one strike. 1 strike within 1 hour:',
    )
  })
})

describe('rateLimitError', () => {
  it('accepts values inside the bounds, edges included', () => {
    expect(rateLimitError({ per_minute: 10000, block_minutes: 1, ban_after_strikes: 100, strike_window_hours: 720 })).toBeNull()
  })

  it('names the first field outside its bounds, the way the service does', () => {
    expect(rateLimitError({ per_minute: 120, block_minutes: 1441, ban_after_strikes: 3, strike_window_hours: 24 })).toBe(
      'block_minutes must be between 1 and 1440',
    )
    expect(rateLimitError({ per_minute: 1.5, block_minutes: 15, ban_after_strikes: 3, strike_window_hours: 24 })).toBe(
      'per_minute must be between 1 and 10000',
    )
  })
})
