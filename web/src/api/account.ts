import { ACCOUNT_PREFIX } from '../config'
import { request } from './client'
import type { Preferences, User } from './types'

export const account = {
  /** Step one of the magic-link flow: 202 and a mail for an allowed address,
   *  403 with code `not_allowed` for any other. */
  requestLink: (email: string) =>
    request<void>(`${ACCOUNT_PREFIX}/auth/request-link`, { method: 'POST', json: { email }, anonymous: true }),

  /** Step two: the link opens /auth/callback?token=... here; this exchanges
   *  the single-use token for the JWT the app then sends as Bearer. */
  exchangeCallback: (token: string) =>
    request<{ jwt: string; user: User }>(`${ACCOUNT_PREFIX}/auth/callback?token=${encodeURIComponent(token)}`, {
      anonymous: true,
    }),

  me: () => request<User>(`${ACCOUNT_PREFIX}/me`),

  /** Any subset: a value sets, null clears, an absent key stays. Returns the
   *  updated user; the shared demo user gets 403. */
  savePreferences: (p: Partial<Preferences>) =>
    request<User>(`${ACCOUNT_PREFIX}/me/preferences`, { method: 'PUT', json: p }),

  redeemVoucher: (code: string) => request<User>(`${ACCOUNT_PREFIX}/vouchers/redeem`, { method: 'POST', json: { code } }),

  /** Fire-and-forget page view for the aggregated visitor log. */
  recordVisit: (path: string) => request<void>(`${ACCOUNT_PREFIX}/visits`, { method: 'POST', json: { path } }),
}
