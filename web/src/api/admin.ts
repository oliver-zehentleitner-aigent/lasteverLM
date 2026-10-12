import { ACCOUNT_PREFIX, ADMIN_MOCK } from '../config'
import { request } from './client'
import type { AccessEntry, AdminUser, Ban, Block, LoginEvent, Smtp, VisitBucket } from './types'

/** Everything the admin panel needs, as one interface so the pages do not
 *  care whether they talk to the account service or to the mock below.
 *  Paths and shapes follow the account section of the family contract. */
export interface AdminApi {
  listUsers(): Promise<AdminUser[]>
  listLogins(limit: number): Promise<LoginEvent[]>
  listVisits(days: number): Promise<VisitBucket[]>
  getSmtp(): Promise<Smtp>
  saveSmtp(s: Smtp): Promise<Smtp>
  testSmtp(): Promise<void>
  getAllowedDomains(): Promise<string[]>
  saveAllowedDomains(domains: string[]): Promise<string[]>
  /** Codes are shown once; the server stores only their hashes. */
  createVouchers(amountCents: number, count: number): Promise<string[]>
  /** rate limiting and blocking, read-only except for lifting a ban */
  listBlocks(): Promise<Block[]>
  listBans(includeLifted: boolean): Promise<Ban[]>
  liftBan(ip: string): Promise<void>
  listAccess(limit: number): Promise<AccessEntry[]>
}

const A = `${ACCOUNT_PREFIX}/admin`
type Domains = { allowed_domains: string[] }

const httpAdmin: AdminApi = {
  listUsers: () => request<AdminUser[]>(`${A}/users`),
  listLogins: (limit) => request<LoginEvent[]>(`${A}/logins?limit=${limit}`),
  listVisits: (days) => request<VisitBucket[]>(`${A}/visits?days=${days}`),
  getSmtp: () => request<Smtp>(`${A}/settings/smtp`),
  saveSmtp: (s) => request<Smtp>(`${A}/settings/smtp`, { method: 'PUT', json: s }),
  testSmtp: () => request<void>(`${A}/settings/smtp/test`, { method: 'POST' }),
  getAllowedDomains: () => request<Domains>(`${A}/settings/domains`).then((d) => d.allowed_domains),
  saveAllowedDomains: (allowed_domains) =>
    request<Domains>(`${A}/settings/domains`, { method: 'PUT', json: { allowed_domains } }).then((d) => d.allowed_domains),
  createVouchers: (amount_cents, count) =>
    request<{ codes: string[] }>(`${A}/vouchers`, { method: 'POST', json: { amount_cents, count } }).then((r) => r.codes),
  listBlocks: () => request<Block[]>(`${A}/blocks`),
  listBans: (includeLifted) => request<Ban[]>(`${A}/bans?include_lifted=${includeLifted}`),
  liftBan: (ip) => request<void>(`${A}/bans/${encodeURIComponent(ip)}`, { method: 'DELETE' }),
  listAccess: (limit) => request<AccessEntry[]>(`${A}/access?limit=${limit}`),
}

/** In-memory stand-in for local UI work without an account service. */
function mockAdmin(): AdminApi {
  const delay = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 150))
  const users: AdminUser[] = [
    { id: 'u1', email: 'admin@example.org', is_admin: true, balance_cents: 1250, usage_cents: 310, created_at: '2026-10-01T10:00:00Z', last_login_at: '2026-10-12T18:02:00Z' },
    { id: 'u2', email: 'reader@example.org', is_admin: false, balance_cents: 0, usage_cents: 1000, created_at: '2026-10-05T08:00:00Z', last_login_at: '2026-10-11T09:40:00Z' },
    { id: 'u3', email: 'new@example.org', is_admin: false, balance_cents: 1000, usage_cents: 0, created_at: '2026-10-12T17:00:00Z', last_login_at: null },
  ]
  const logins: LoginEvent[] = [
    { user_id: 'u1', email: 'admin@example.org', at: '2026-10-12T18:02:00Z' },
    { user_id: 'u2', email: 'reader@example.org', at: '2026-10-11T09:40:00Z' },
  ]
  const visits: VisitBucket[] = [
    { day: '2026-10-12', path: '/', visits: 23, unique: 7 },
    { day: '2026-10-12', path: '/admin', visits: 4, unique: 1 },
    { day: '2026-10-11', path: '/', visits: 9, unique: 3 },
  ]
  const blocks: Block[] = [{ ip: '203.0.113.7', blocked_until: '2026-10-12T20:30:00Z', strikes: 3, updated_at: '2026-10-12T20:15:00Z' }]
  let bans: Ban[] = [
    { ip: '198.51.100.23', reason: 'repeated blocks', created_at: '2026-10-11T22:00:00Z', lifted_at: null },
    { ip: '192.0.2.44', reason: 'abuse report', created_at: '2026-10-09T10:00:00Z', lifted_at: '2026-10-10T08:00:00Z' },
  ]
  const access: AccessEntry[] = [
    { at: '2026-10-12T20:16:00Z', ip: '203.0.113.7', method: 'POST', path: '/api/account/auth/request-link', status: 429, user_id: null, service: 'account' },
    { at: '2026-10-12T20:15:30Z', ip: '198.51.100.9', method: 'POST', path: '/api/rag/notebooks/n1/ask', status: 200, user_id: 'u1', service: 'rag' },
  ]
  let smtp: Smtp = { host: 'smtp.example.org', port: 587, username: 'mailer', from_address: 'no-reply@example.org', starttls: true }
  let domains = ['example.org']

  return {
    listUsers: () => delay([...users]),
    listLogins: (limit) => delay(logins.slice(0, limit)),
    listVisits: () => delay([...visits]),
    getSmtp: () => delay({ ...smtp }),
    saveSmtp: (s) => {
      smtp = { ...s, password: undefined }
      return delay({ ...smtp })
    },
    testSmtp: () => delay(undefined),
    getAllowedDomains: () => delay([...domains]),
    saveAllowedDomains: (d) => {
      domains = [...d]
      return delay([...domains])
    },
    createVouchers: (_amount, count) =>
      delay(Array.from({ length: count }, () => `V-${Math.random().toString(36).slice(2, 8).toUpperCase()}`)),
    listBlocks: () => delay([...blocks]),
    listBans: (includeLifted) => delay(bans.filter((b) => includeLifted || b.lifted_at === null)),
    liftBan: (ip) => {
      bans = bans.map((b) => (b.ip === ip && b.lifted_at === null ? { ...b, lifted_at: new Date().toISOString() } : b))
      return delay(undefined)
    },
    listAccess: (limit) => delay(access.slice(0, limit)),
  }
}

export const admin: AdminApi = ADMIN_MOCK ? mockAdmin() : httpAdmin
