import { ACCOUNT_PREFIX } from '../config'
import { request } from './client'
import type { Health, MyCredit, Preferences, PublicPrices, User } from './types'

export const account = {
  /** the public price list; no login, cached five minutes by the service */
  prices: () => request<PublicPrices>(`${ACCOUNT_PREFIX}/prices`, { anonymous: true }),

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

  /** public; carries the build (version, commit) once core reports it */
  health: () => request<Health>(`${ACCOUNT_PREFIX}/healthz`, { anonymous: true }),

  /** Any subset: a value sets, null clears, an absent key stays. Returns the
   *  updated user; the shared demo user gets 403. */
  savePreferences: (p: Partial<Preferences>) =>
    request<User>(`${ACCOUNT_PREFIX}/me/preferences`, { method: 'PUT', json: p }),

  /** the user's own credit for a range of days, newest entries first, a page at a time (limit ≤ 200) */
  credit: (from: string, to: string, offset = 0, limit = 50) =>
    request<MyCredit>(`${ACCOUNT_PREFIX}/me/credit?from=${from}&to=${to}&limit=${limit}&offset=${offset}`),
  redeemVoucher: (code: string) => request<User>(`${ACCOUNT_PREFIX}/vouchers/redeem`, { method: 'POST', json: { code } }),

  /** Fire-and-forget page view for the aggregated visitor log. */
  recordVisit: (path: string) => request<void>(`${ACCOUNT_PREFIX}/visits`, { method: 'POST', json: { path } }),
}
