import { ACCOUNT_PREFIX, ADMIN_MOCK, INGEST_PREFIX, RAG_PREFIX } from '../config'
import { request } from './client'
import type {
  AccessEntry,
  AccountDay,
  AccountStats,
  AccountUsage,
  AdminUser,
  UserRole,
  LoginAttempt,
  AllowKind,
  Allowlist,
  Ban,
  Block,
  IngestDay,
  IngestStats,
  LoginEvent,
  RagDay,
  RagStats,
  RateLimitRules,
  RateLimitUpdate,
  Smtp,
  SystemInfo,
  VisitBucket,
  Voucher,
} from './types'

/** Everything the admin panel needs, as one interface so the pages do not
 *  care whether they talk to the account service or to the mock below.
 *  Paths and shapes follow the account section of the family contract;
 *  the three stats endpoints are one per service. */
export interface AdminApi {
  accountStats(): Promise<AccountStats>
  ingestStats(): Promise<IngestStats>
  ragStats(): Promise<RagStats>
  /** daily series for the statistics charts, one endpoint per service */
  accountDaily(days: number): Promise<AccountDay[]>
  accountUsage(): Promise<AccountUsage>
  ingestDaily(days: number): Promise<IngestDay[]>
  ragDaily(days: number): Promise<RagDay[]>
  listUsers(): Promise<AdminUser[]>
  listLogins(limit: number): Promise<LoginEvent[]>
  /** sign-in link requests, newest first */
  listLoginAttempts(limit: number): Promise<LoginAttempt[]>
  listVisits(days: number): Promise<VisitBucket[]>
  getSmtp(): Promise<Smtp>
  /** versions, health, pods and deployments of the running system */
  system(): Promise<SystemInfo>
  testSmtp(): Promise<{ sent_to: string }>
  getAllowlist(): Promise<Allowlist>
  /** one entry at a time; the server normalizes it and returns both lists */
  addAllowed(kind: AllowKind, value: string): Promise<Allowlist>
  /** admin only; 409 for the last admin or the demo user */
  setRole(userId: string, role: UserRole): Promise<AdminUser>
  removeAllowed(kind: AllowKind, value: string): Promise<void>
  /** Codes are shown once; the server stores only their hashes. */
  createVouchers(amountCents: number, count: number): Promise<string[]>
  /** newest first, without codes */
  listVouchers(limit: number): Promise<Voucher[]>
  /** open vouchers only; a redeemed one answers 409 */
  deleteVoucher(id: string): Promise<void>
  /** the rule for every service; PUT the four editable fields, DELETE back to the environment */
  getRateLimit(): Promise<RateLimitRules>
  saveRateLimit(u: RateLimitUpdate): Promise<RateLimitRules>
  resetRateLimit(): Promise<void>
  /** rate limiting and blocking, read-only except for lifting a ban */
  listBlocks(): Promise<Block[]>
  listBans(includeLifted: boolean): Promise<Ban[]>
  liftBan(ip: string): Promise<void>
  listAccess(limit: number): Promise<AccessEntry[]>
}

const A = `${ACCOUNT_PREFIX}/admin`
const ALLOW_PATH: Record<AllowKind, string> = { domain: 'domains', address: 'addresses', viewer: 'viewer-domains' }
// the body names the value: {"domain"} for both domain lists, {"address"} for addresses
const ALLOW_FIELD: Record<AllowKind, string> = { domain: 'domain', address: 'address', viewer: 'domain' }

const httpAdmin: AdminApi = {
  accountStats: () => request<AccountStats>(`${A}/stats`),
  ingestStats: () => request<IngestStats>(`${INGEST_PREFIX}/admin/stats`),
  ragStats: () => request<RagStats>(`${RAG_PREFIX}/admin/stats`),
  accountDaily: (days) => request<{ days: AccountDay[] }>(`${A}/stats/daily?days=${days}`).then((r) => r.days),
  accountUsage: () => request<AccountUsage>(`${A}/stats/usage`),
  ingestDaily: (days) => request<{ days: IngestDay[] }>(`${INGEST_PREFIX}/admin/stats/daily?days=${days}`).then((r) => r.days),
  ragDaily: (days) => request<{ days: RagDay[] }>(`${RAG_PREFIX}/admin/stats/daily?days=${days}`).then((r) => r.days),
  listUsers: () => request<AdminUser[]>(`${A}/users`),
  setRole: (userId, role) => request<AdminUser>(`${A}/users/${encodeURIComponent(userId)}`, { method: 'PATCH', json: { role } }),
  listLogins: (limit) => request<LoginEvent[]>(`${A}/logins?limit=${limit}`),
  listLoginAttempts: (limit) => request<LoginAttempt[]>(`${A}/login-attempts?limit=${limit}`),
  listVisits: (days) => request<VisitBucket[]>(`${A}/visits?days=${days}`),
  getSmtp: () => request<Smtp>(`${A}/settings/smtp`),
  system: () => request<SystemInfo>(`${A}/system`),
  testSmtp: () => request<{ sent_to: string }>(`${A}/settings/smtp/test`, { method: 'POST' }),
  getAllowlist: () => request<Allowlist>(`${A}/settings/allowlist`),
  addAllowed: (kind, value) =>
    request<Allowlist>(`${A}/settings/${ALLOW_PATH[kind]}`, { method: 'POST', json: { [ALLOW_FIELD[kind]]: value } }),
  removeAllowed: (kind, value) =>
    request<void>(`${A}/settings/${ALLOW_PATH[kind]}/${encodeURIComponent(value)}`, { method: 'DELETE' }),
  createVouchers: (amount_cents, count) =>
    request<{ codes: string[] }>(`${A}/vouchers`, { method: 'POST', json: { amount_cents, count } }).then((r) => r.codes),
  listVouchers: (limit) => request<Voucher[]>(`${A}/vouchers?limit=${limit}`),
  deleteVoucher: (id) => request<void>(`${A}/vouchers/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  getRateLimit: () => request<RateLimitRules>(`${A}/settings/ratelimit`),
  saveRateLimit: (u) => request<RateLimitRules>(`${A}/settings/ratelimit`, { method: 'PUT', json: u }),
  resetRateLimit: () => request<void>(`${A}/settings/ratelimit`, { method: 'DELETE' }),
  listBlocks: () => request<Block[]>(`${A}/blocks`),
  listBans: (includeLifted) => request<Ban[]>(`${A}/bans?include_lifted=${includeLifted}`),
  // the key is an IPv4 address or an IPv6 /64 prefix ("2001:db8:1:2::/64");
  // as a query parameter its slash never reaches the path
  liftBan: (ip) => request<void>(`${A}/bans?ip=${encodeURIComponent(ip)}`, { method: 'DELETE' }),
  listAccess: (limit) => request<AccessEntry[]>(`${A}/access?limit=${limit}`),
}

/** UTC days ending today, oldest first, with a deterministic wobble so the
 *  mock charts look like traffic without changing on every reload. */
function mockDays<T>(days: number, make: (i: number, wobble: (scale: number) => number, day: string) => T): T[] {
  const today = new Date()
  let seed = 7
  const wobble = (scale: number) => {
    seed = (seed * 16807) % 2147483647
    return Math.round((seed / 2147483647) * scale)
  }
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - (days - 1 - i)))
    return make(i, wobble, d.toISOString().slice(0, 10))
  })
}

/** In-memory stand-in for local UI work without an account service. */
function mockAdmin(): AdminApi {
  const delay = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 150))
  const users: AdminUser[] = [
    { id: 'u1', email: 'admin@example.org', is_admin: true, role: 'admin', balance_cents: 1250, usage_cents: 310, granted_cents: 1560, created_at: '2026-10-01T10:00:00Z', last_login_at: '2026-10-12T18:02:00Z' },
    { id: 'u2', email: 'reader@example.org', is_admin: false, role: 'viewer', balance_cents: 0, usage_cents: 1000, granted_cents: 1000, created_at: '2026-10-05T08:00:00Z', last_login_at: '2026-10-11T09:40:00Z' },
    { id: 'u3', email: 'new@example.org', is_admin: false, role: 'user', balance_cents: 1000, usage_cents: 0, granted_cents: 1000, created_at: '2026-10-12T17:00:00Z', last_login_at: null },
  ]
  const logins: LoginEvent[] = [
    { user_id: 'u1', email: 'admin@example.org', at: '2026-10-12T18:02:00Z' },
    { user_id: 'u2', email: 'reader@example.org', at: '2026-10-11T09:40:00Z' },
  ]
  const attempts: LoginAttempt[] = [
    { at: '2026-10-12T18:01:30Z', email: 'admin@example.org', ip: '198.51.100.9', outcome: 'allowed' },
    { at: '2026-10-12T17:55:00Z', email: 'someone@elsewhere.test', ip: '203.0.113.7', outcome: 'refused' },
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
    { ip: '2001:db8:1:2::/64', reason: 'repeated blocks', created_at: '2026-10-12T09:30:00Z', lifted_at: null },
  ]
  const access: AccessEntry[] = [
    { at: '2026-10-12T20:16:00Z', ip: '203.0.113.7', method: 'POST', path: '/api/account/auth/request-link', status: 429, user_id: null, service: 'account' },
    { at: '2026-10-12T20:15:30Z', ip: '198.51.100.9', method: 'POST', path: '/api/rag/notebooks/n1/ask', status: 200, user_id: 'u1', service: 'rag' },
  ]
  const RULE_DEFAULTS: RateLimitRules = { per_minute: 120, block_minutes: 15, ban_after_strikes: 3, strike_window_hours: 24, ban_max_days: 90, retention_days: 30 }
  let rules = { ...RULE_DEFAULTS }
  const smtp: Smtp = { host: 'smtp.example.org', port: 587, username: 'mailer', from_address: 'no-reply@example.org', starttls: true }
  let allow: Required<Allowlist> = { allowed_domains: ['example.org', 'review.example.org'], allowed_addresses: ['guest@partner.test'], viewer_domains: ['review.example.org'] }
  const listKey = (kind: AllowKind) => (kind === 'domain' ? 'allowed_domains' : kind === 'viewer' ? 'viewer_domains' : 'allowed_addresses')
  let vouchers: Voucher[] = [
    { id: 'v2', amount_cents: 500, created_by: 'admin@example.org', created_at: '2026-10-12T17:30:00Z', redeemed_by: null, redeemed_at: null, status: 'open' },
    { id: 'v1', amount_cents: 1000, created_by: 'admin@example.org', created_at: '2026-10-10T09:00:00Z', redeemed_by: 'reader@example.org', redeemed_at: '2026-10-11T09:45:00Z', status: 'redeemed' },
  ]

  return {
    accountStats: () =>
      delay({
        users: users.length,
        logins_24h: 1,
        vouchers: { issued: vouchers.length, redeemed: 1, open: vouchers.length - 1 },
        credits_granted_cents: 3000,
        usage_cost_cents: { total: 1310, last_24h: 120 },
        blocks_active: blocks.length,
        bans_active: bans.filter((b) => b.lifted_at === null).length,
      }),
    ingestStats: () =>
      delay({ sources: { processing: 1, ready: 12, failed: 1 }, jobs: { pending: 0, running: 1, failed: 1 }, chunks: 640, source_bytes: 18_400_000 }),
    ragStats: () =>
      delay({
        notebooks: { total: 4 },
        messages: { total: 38, last_24h: 5 },
        outputs: {
          by_kind: { report: 3, quiz: 2, table: 1, mindmap: 1, infographic: 0, audio: 1 },
          by_status: { waiting: 0, processing: 1, ready: 6, failed: 1 },
        },
        jobs: { pending: 0, running: 1, failed: 1 },
        shared: { outputs: 2 },
      }),
    accountDaily: (days) =>
      delay(
        mockDays(days, (i, w, day) => ({
          day,
          logins: 2 + w(6) + Math.round(i / 6),
          visits: 10 + w(25) + i,
          usage_cost_cents: 20 + w(140) + i * 3,
          credits_granted_cents: i % 7 === 3 ? 500 * (1 + w(2)) : 0,
        })),
      ),
    accountUsage: () =>
      delay({
        by_model: [
          { model: 'gpt-oss-120b', kind: 'llm' as const, calls: 412, cost_cents: 2210 },
          { model: 'tts-1', kind: 'tts' as const, calls: 18, cost_cents: 640 },
          { model: 'text-embedding-3-small', kind: 'embedding' as const, calls: 960, cost_cents: 95 },
        ],
        top_users: users.map((u) => ({ email: u.email, usage_cents: u.usage_cents, balance_cents: u.balance_cents })).sort((a, b) => b.usage_cents - a.usage_cents),
      }),
    ingestDaily: (days) =>
      delay(
        mockDays(days, (_i, w, day) => {
          const by = { pdf: w(4), text: w(3), url: w(2), image: w(2) }
          const created = by.pdf + by.text + by.url + by.image
          return { day, sources_created: created, by_kind: by, failed: Math.min(created, w(1)) }
        }),
      ),
    ragDaily: (days) =>
      delay(
        mockDays(days, (i, w, day) => {
          const by = { report: w(3), quiz: w(2), table: w(2), mindmap: w(2), infographic: w(1), audio: w(1) }
          return { day, messages: 6 + w(30) + i, outputs: Object.values(by).reduce((a, b) => a + b, 0), outputs_by_kind: by }
        }),
      ),
    listUsers: () => delay([...users]),
    setRole: (userId, role) => {
      const u = users.find((x) => x.id === userId)
      if (!u) return Promise.reject(new Error('unknown user'))
      if (u.role === 'admin' && role !== 'admin' && users.filter((x) => x.role === 'admin').length === 1) return Promise.reject(new Error('the last admin cannot be demoted'))
      Object.assign(u, { role, is_admin: role === 'admin' })
      return delay({ ...u })
    },
    listLogins: (limit) => delay(logins.slice(0, limit)),
    listLoginAttempts: (limit) => delay(attempts.slice(0, limit)),
    listVisits: () => delay([...visits]),
    getSmtp: () => delay({ ...smtp }),
    system: () =>
      delay({
        version: '0.6.1',
        commit: '5e320ae9f0c1',
        cluster: true,
        services: [
          { name: 'account' as const, version: '0.6.1', commit: '5e320ae', healthy: true },
          { name: 'ingest' as const, version: '0.6.1', commit: '5e320ae', healthy: true },
          { name: 'rag' as const, version: null, commit: null, healthy: false },
        ],
        pods: [
          { name: 'lasteverlm-account-7d9f-x2k4p', service: 'account', image_tag: '0.6.1', ready: true, restarts: 0, node: 'pool-a-1', started_at: '2026-10-13T18:02:00Z' },
          { name: 'lasteverlm-rag-worker-5c8b-q8n2m', service: 'rag', image_tag: '0.6.1', ready: false, restarts: 3, node: 'pool-a-2', started_at: '2026-10-13T18:05:00Z' },
        ],
        deployments: [
          { name: 'lasteverlm-account', replicas: 1, ready: 1, updated: 1 },
          { name: 'lasteverlm-rag-worker', replicas: 2, ready: 1, updated: 2 },
        ],
      }),
    testSmtp: () => delay({ sent_to: 'admin@example.org' }),
    getAllowlist: () => delay({ ...allow }),
    addAllowed: (kind, value) => {
      const v = value.trim().toLowerCase().replace(/^@/, '')
      const key = listKey(kind)
      if (allow[key].includes(v)) return Promise.reject(new Error('already listed'))
      allow = { ...allow, [key]: [...allow[key], v].sort() }
      return delay({ ...allow })
    },
    removeAllowed: (kind, value) => {
      const key = listKey(kind)
      allow = { ...allow, [key]: allow[key].filter((x) => x !== value) }
      return delay(undefined)
    },
    createVouchers: (amount, count) => {
      const codes = Array.from({ length: count }, () => `V-${Math.random().toString(36).slice(2, 8).toUpperCase()}`)
      const now = new Date().toISOString()
      vouchers = [
        ...codes.map((_, i) => ({ id: `v${vouchers.length + i + 1}`, amount_cents: amount, created_by: 'admin@example.org', created_at: now, redeemed_by: null, redeemed_at: null, status: 'open' as const })),
        ...vouchers,
      ]
      return delay(codes)
    },
    listVouchers: (limit) => delay(vouchers.slice(0, limit)),
    deleteVoucher: (id) => {
      if (vouchers.some((v) => v.id === id && v.status === 'redeemed')) return Promise.reject(new Error('voucher already redeemed'))
      vouchers = vouchers.filter((v) => v.id !== id)
      return delay(undefined)
    },
    getRateLimit: () => delay({ ...rules }),
    saveRateLimit: (u) => {
      rules = { ...rules, ...u }
      return delay({ ...rules })
    },
    resetRateLimit: () => {
      rules = { ...RULE_DEFAULTS }
      return delay(undefined)
    },
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
