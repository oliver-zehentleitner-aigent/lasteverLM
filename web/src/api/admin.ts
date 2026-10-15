import { ACCOUNT_PREFIX, ADMIN_MOCK, INGEST_PREFIX, RAG_PREFIX } from '../config'
import { ApiError, request } from './client'
import type {
  AdminOutputMatch,
  AdminOutputSearch,
  FeedbackStats,
  StarterNotebook,
  ExchangeRateStatus,
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
  CostGroup,
  FinanceCosts,
  FinanceInfra,
  FinanceProfit,
  FinanceRevenue,
  InfraEntry,
  PricingRules,
  PricingView,
  VoucherSend,
} from './types'

/** Everything the admin panel needs, as one interface so the pages do not
 *  care whether they talk to the account service or to the mock below.
 *  Paths and shapes follow the account section of the family contract;
 *  the three stats endpoints are one per service. */
export interface AdminApi {
  accountStats(): Promise<AccountStats>
  ingestStats(): Promise<IngestStats>
  ragStats(): Promise<RagStats>
  /** answer ratings per day and the newest down-rated answers */
  feedback(days: number): Promise<FeedbackStats>
  /** outputs whose ID starts with a prefix (6–32 hex characters), from rag */
  findOutputs(prefix: string): Promise<AdminOutputSearch>
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
  /** finance: from/to are UTC dates, inclusive */
  financeInfra(from: string, to: string): Promise<FinanceInfra>
  addInfra(e: { date: string; item: string; amount_cents: number; currency: 'EUR' | 'USD' }): Promise<InfraEntry>
  /** manual lines only; 409 not_manual for a Vultr line */
  deleteInfra(id: string): Promise<void>
  /** 409 vultr_not_connected, 502 vultr_failed */
  syncInfra(): Promise<FinanceInfra>
  /** viewer and admin */
  getStarter(): Promise<StarterNotebook>
  /** admin; 404 unknown_notebook, 409 owner_not_admin, 409 sources_not_ready */
  setStarter(notebookId: string): Promise<StarterNotebook>
  clearStarter(): Promise<void>
  getPricing(): Promise<PricingView>
  savePricing(rules: PricingRules): Promise<PricingView>
  /** the view for these rules, not stored */
  previewPricing(rules: PricingRules): Promise<PricingView>
  resetPricing(): Promise<void>
  /** automatic fetches the ECB rate at once; manual pauses the hourly update */
  setRateMode(mode: ExchangeRateStatus['mode']): Promise<PricingView>
  /** fetch the ECB rate now; a failure shows in `rate.last_error` */
  syncRate(): Promise<PricingView>
  financeCosts(from: string, to: string, group: CostGroup): Promise<FinanceCosts>
  financeRevenue(from: string, to: string): Promise<FinanceRevenue>
  financeProfit(from: string, to: string, group: 'month' | 'day'): Promise<FinanceProfit>
  setVoucherPaid(id: string, paid: boolean): Promise<Voucher>
  /** versions, health, pods and deployments of the running system */
  system(): Promise<SystemInfo>
  testSmtp(): Promise<{ sent_to: string }>
  getAllowlist(): Promise<Allowlist>
  /** one entry at a time; the server normalizes it and returns both lists */
  addAllowed(kind: AllowKind, value: string): Promise<Allowlist>
  /** admin only; 409 for the last admin or the demo user */
  setRole(userId: string, role: UserRole): Promise<AdminUser>
  /** The account and everything it owns, in every service. 409 for the
   *  caller's own account and the demo user; 502 with `{step, message}`
   *  when a service failed, and then the user is still there. */
  deleteUser(userId: string): Promise<void>
  removeAllowed(kind: AllowKind, value: string): Promise<void>
  /** The new codes come back once here; an admin can show one again later (`voucherCode`, kept encrypted). */
  /** with `send`, each created voucher is mailed right away */
  /** `paid`: sold for their face value (revenue) rather than given away */
  createVouchers(amountCents: number, count: number, send?: VoucherSend, paid?: boolean): Promise<string[]>
  /** admin only; 404 with code `not_recoverable` for a voucher made before codes were kept */
  voucherCode(id: string): Promise<string>
  /** the updated row; 409 already_redeemed / smtp_not_configured, 404 not_recoverable, 429 too_many_mails, 502 mail_failed */
  sendVoucher(id: string, send: VoucherSend): Promise<Voucher>
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
const ALLOW_PATH: Record<AllowKind, string> = { domain: 'domains', address: 'addresses', viewer: 'viewer-domains', viewer_address: 'viewer-addresses' }
// the body names the value: {"domain"} for both domain lists, {"address"} for addresses
const ALLOW_FIELD: Record<AllowKind, string> = { domain: 'domain', address: 'address', viewer: 'domain', viewer_address: 'address' }

const httpAdmin: AdminApi = {
  accountStats: () => request<AccountStats>(`${A}/stats`),
  ingestStats: () => request<IngestStats>(`${INGEST_PREFIX}/admin/stats`),
  ragStats: () => request<RagStats>(`${RAG_PREFIX}/admin/stats`),
  feedback: (days) => request<FeedbackStats>(`${RAG_PREFIX}/admin/feedback?days=${days}`),
  findOutputs: (prefix) => request<AdminOutputSearch>(`${RAG_PREFIX}/admin/outputs?id_prefix=${encodeURIComponent(prefix)}`),
  accountDaily: (days) => request<{ days: AccountDay[] }>(`${A}/stats/daily?days=${days}`).then((r) => r.days),
  accountUsage: () => request<AccountUsage>(`${A}/stats/usage`),
  ingestDaily: (days) => request<{ days: IngestDay[] }>(`${INGEST_PREFIX}/admin/stats/daily?days=${days}`).then((r) => r.days),
  ragDaily: (days) => request<{ days: RagDay[] }>(`${RAG_PREFIX}/admin/stats/daily?days=${days}`).then((r) => r.days),
  listUsers: () => request<AdminUser[]>(`${A}/users`),
  setRole: (userId, role) => request<AdminUser>(`${A}/users/${encodeURIComponent(userId)}`, { method: 'PATCH', json: { role } }),
  deleteUser: (userId) => request<void>(`${A}/users/${encodeURIComponent(userId)}`, { method: 'DELETE' }),
  listLogins: (limit) => request<LoginEvent[]>(`${A}/logins?limit=${limit}`),
  listLoginAttempts: (limit) => request<LoginAttempt[]>(`${A}/login-attempts?limit=${limit}`),
  listVisits: (days) => request<VisitBucket[]>(`${A}/visits?days=${days}`),
  getSmtp: () => request<Smtp>(`${A}/settings/smtp`),
  financeInfra: (from, to) => request<FinanceInfra>(`${A}/finance/infra?from=${from}&to=${to}`),
  addInfra: (e) => request<InfraEntry>(`${A}/finance/infra`, { method: 'POST', json: e }),
  deleteInfra: (id) => request<void>(`${A}/finance/infra/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  syncInfra: () => request<FinanceInfra>(`${A}/finance/infra/sync`, { method: 'POST' }),
  getStarter: () => request<StarterNotebook>(`${A}/settings/starter-notebook`),
  setStarter: (notebookId) => request<StarterNotebook>(`${A}/settings/starter-notebook`, { method: 'PUT', json: { notebook_id: notebookId } }),
  clearStarter: () => request<void>(`${A}/settings/starter-notebook`, { method: 'DELETE' }),
  getPricing: () => request<PricingView>(`${A}/settings/pricing`),
  savePricing: (rules) => request<PricingView>(`${A}/settings/pricing`, { method: 'PUT', json: rules }),
  previewPricing: (rules) => request<PricingView>(`${A}/settings/pricing/preview`, { method: 'POST', json: rules }),
  resetPricing: () => request<void>(`${A}/settings/pricing`, { method: 'DELETE' }),
  setRateMode: (mode) => request<PricingView>(`${A}/settings/pricing/rate-mode`, { method: 'PUT', json: { mode } }),
  syncRate: () => request<PricingView>(`${A}/settings/pricing/rate/sync`, { method: 'POST' }),
  financeCosts: (from, to, group) => request<FinanceCosts>(`${A}/finance/costs?from=${from}&to=${to}&group=${group}`),
  financeRevenue: (from, to) => request<FinanceRevenue>(`${A}/finance/revenue?from=${from}&to=${to}`),
  financeProfit: (from, to, group) => request<FinanceProfit>(`${A}/finance/profit?from=${from}&to=${to}&group=${group}`),
  setVoucherPaid: (id, paid) => request<Voucher>(`${A}/vouchers/${encodeURIComponent(id)}`, { method: 'PATCH', json: { paid } }),
  system: () => request<SystemInfo>(`${A}/system`),
  testSmtp: () => request<{ sent_to: string }>(`${A}/settings/smtp/test`, { method: 'POST' }),
  getAllowlist: () => request<Allowlist>(`${A}/settings/allowlist`),
  addAllowed: (kind, value) =>
    request<Allowlist>(`${A}/settings/${ALLOW_PATH[kind]}`, { method: 'POST', json: { [ALLOW_FIELD[kind]]: value } }),
  removeAllowed: (kind, value) =>
    request<void>(`${A}/settings/${ALLOW_PATH[kind]}/${encodeURIComponent(value)}`, { method: 'DELETE' }),
  createVouchers: (amount_cents, count, send, paid) =>
    request<{ codes: string[] }>(`${A}/vouchers`, {
      method: 'POST',
      json: { amount_cents, count, ...(paid !== undefined ? { paid } : {}), ...(send ? { send_to: send.email, message: send.message, allow: send.allow } : {}) },
    }).then((r) => r.codes),
  voucherCode: (id) => request<{ code: string }>(`${A}/vouchers/${encodeURIComponent(id)}/code`).then((r) => r.code),
  sendVoucher: (id, send) => request<Voucher>(`${A}/vouchers/${encodeURIComponent(id)}/send`, { method: 'POST', json: send }),
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
  const mockOutputs: AdminOutputMatch[] = [
    {
      id: '3f9c21ab-0d4e-4c1a-9b7e-1234567890ab',
      notebook_id: 'n1',
      notebook_title: 'Dead reckoning',
      kind: 'report',
      title: 'Dead reckoning: a report',
      status: 'failed',
      error: 'the model did not answer',
      created_at: '2026-10-15T12:56:00Z',
      finished_at: '2026-10-15T12:58:10Z',
      deleted_at: null,
      owner: { id: 'u3', email: 'new@example.org' },
      attempts: 2,
      attempt_log: [
        { at: '2026-10-15T12:57:00Z', attempt: 1, model: 'glm-4.6', error_kind: 'timeout', provider_status: null, message: 'the model did not answer in time', service: 'rag' },
        { at: '2026-10-15T12:58:10Z', attempt: 2, model: 'glm-4.6', error_kind: 'provider_refused', provider_status: 429, message: 'the provider is limiting requests', service: 'rag' },
      ],
    },
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
  let allow: Required<Allowlist> = { allowed_domains: ['example.org', 'review.example.org'], allowed_addresses: ['guest@partner.test'], viewer_domains: ['review.example.org'], viewer_addresses: [] }
  const listKey = (kind: AllowKind) =>
    kind === 'domain' ? 'allowed_domains' : kind === 'viewer' ? 'viewer_domains' : kind === 'viewer_address' ? 'viewer_addresses' : 'allowed_addresses'
  let infra: FinanceInfra = {
    configured: false,
    last_success_at: null,
    last_attempt_at: null,
    last_error: null,
    usd_per_eur: 1.1188,
    entries: [
      { id: 'i1', date: '2026-10-01', source: 'manual', item: 'Domain', amount_cents: 1500, currency: 'EUR', amount_eur_cents: 1500 },
      { id: 'i2', date: '2026-10-02', source: 'vultr', item: 'VKE cluster', amount_cents: 2400, currency: 'USD', amount_eur_cents: 2145.16 },
    ],
    totals_by_currency: { EUR: 1500, USD: 2400 },
    total_eur_cents: 3645.16,
  }
  let starter: StarterNotebook = { notebook_id: null, owner_id: null, set_at: null, set_by: null }
  let pricing: PricingRules = { usd_per_eur: 1.1188, default_margin_pct: 30, actions: { 'output:audio': { fixed_cents: 2 } } }
  const checked = new Date(Date.now() - 55 * 60 * 1000).toISOString()
  let rate: ExchangeRateStatus = { usd_per_eur: 1.1188, mode: 'automatic', source: 'ECB', rate_date: '2026-10-13', last_checked: checked, last_success: checked, last_error: null, stale: false }
  const pricingView = (r: PricingRules): PricingView => {
    const actions = ['chat_answer', 'output:report', 'output:audio', 'source:pdf', 'judge']
    return {
      rules: r,
      actions,
      rate: { ...rate, usd_per_eur: r.usd_per_eur },
      preview: actions.map((a, i) => {
        const margin = r.actions[a]?.margin_pct ?? r.default_margin_pct
        const fixed = r.actions[a]?.fixed_cents ?? 0
        const cost = [0.42, 2.1, 9.8, 0.35, 1.2][i]
        return { action: a, actions: [120, 14, 3, 40, 6][i], avg_cost_cents: cost, margin_pct: margin, fixed_cents: fixed, charge_cents: cost * (1 + margin / 100) + fixed }
      }),
    }
  }
  let mockCodes: Record<string, string> = {}
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
    feedback: (days) =>
      delay({
        days: Array.from({ length: days }, (_, i) => ({ day: new Date(Date.now() - (days - 1 - i) * 86_400_000).toISOString().slice(0, 10), up: i % 3, down: i % 7 === 0 ? 1 : 0 })),
        latest_down: [{ message_id: 'm1', notebook_id: 'nb1', at: '2026-10-14T10:00:00Z', comment: 'cites the wrong page', answer: 'The method is called dead reckoning [1].', question: 'What is the method called?' }],
      }),
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
          const by = { pdf: w(4), text: w(3), url: w(2), image: w(2), audio: w(1) }
          const created = by.pdf + by.text + by.url + by.image + by.audio
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
    findOutputs: (prefix) => delay({ matches: mockOutputs.filter((o) => o.id.replace(/-/g, '').startsWith(prefix)), truncated: false }),
    setRole: (userId, role) => {
      const u = users.find((x) => x.id === userId)
      if (!u) return Promise.reject(new Error('unknown user'))
      if (u.role === 'admin' && role !== 'admin' && users.filter((x) => x.role === 'admin').length === 1) return Promise.reject(new Error('the last admin cannot be demoted'))
      Object.assign(u, { role, is_admin: role === 'admin' })
      return delay({ ...u })
    },
    deleteUser: (userId) => {
      const i = users.findIndex((x) => x.id === userId)
      // the mock's signed-in admin is the first user
      if (i === 0) return Promise.reject(new ApiError(409, 'you cannot delete your own account'))
      if (i < 0) return Promise.reject(new ApiError(404, 'unknown user'))
      users.splice(i, 1)
      return delay(undefined)
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
    createVouchers: (amount, count, send, paid) => {
      const codes = Array.from({ length: count }, () => `V-${Math.random().toString(36).slice(2, 8).toUpperCase()}`)
      const now = new Date().toISOString()
      vouchers = [
        ...codes.map((c, i) => ({
          id: `v${vouchers.length + i + 1}`,
          amount_cents: amount,
          created_by: 'admin@example.org',
          created_at: now,
          redeemed_by: null,
          redeemed_at: null,
          status: 'open' as const,
          code_masked: `${c.slice(0, 4)}-****`,
          recoverable: true,
          sent_to: send?.email ?? null,
          sent_at: send ? now : null,
          paid: paid ?? false,
        })),
        ...vouchers,
      ]
      mockCodes = { ...mockCodes, ...Object.fromEntries(vouchers.slice(0, count).map((v, i) => [v.id, codes[i]])) }
      return delay(codes)
    },
    voucherCode: (id) => (mockCodes[id] ? delay(mockCodes[id]) : Promise.reject(new ApiError(404, 'This voucher was made before codes were kept.', 'not_recoverable'))),
    sendVoucher: (id, send) => {
      const v = vouchers.find((x) => x.id === id)
      if (!v) return Promise.reject(new ApiError(404, 'unknown voucher'))
      if (v.status === 'redeemed') return Promise.reject(new ApiError(409, 'voucher already redeemed', 'already_redeemed'))
      if (!mockCodes[id]) return Promise.reject(new ApiError(404, 'This voucher was made before codes were kept.', 'not_recoverable'))
      Object.assign(v, { sent_to: send.email, sent_at: new Date().toISOString() })
      return delay({ ...v })
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
    // finance: a small world of two weeks, one Vultr line in USD, a margin of 30 %
    financeInfra: () => delay({ ...infra, entries: [...infra.entries] }),
    addInfra: (e) => {
      const entry = { id: `i${infra.entries.length + 1}`, source: 'manual' as const, amount_eur_cents: e.currency === 'EUR' ? e.amount_cents : e.amount_cents / (infra.usd_per_eur ?? 1), ...e }
      infra = { ...infra, entries: [entry, ...infra.entries] }
      return delay(entry)
    },
    deleteInfra: (id) => {
      if (infra.entries.some((x) => x.id === id && x.source === 'vultr')) return Promise.reject(new ApiError(409, 'Vultr lines cannot be deleted', 'not_manual'))
      infra = { ...infra, entries: infra.entries.filter((x) => x.id !== id) }
      return delay(undefined)
    },
    syncInfra: () => Promise.reject(new ApiError(409, 'Vultr is not connected', 'vultr_not_connected')),
    getStarter: () => delay(starter),
    setStarter: (notebookId) => {
      starter = { notebook_id: notebookId, owner_id: 'u-admin', set_at: new Date().toISOString(), set_by: 'admin@example.org' }
      return delay(starter)
    },
    clearStarter: () => {
      starter = { notebook_id: null, owner_id: null, set_at: null, set_by: null }
      return delay(undefined)
    },
    getPricing: () => delay(pricingView(pricing)),
    savePricing: (r) => {
      // another rate is an override, as in the account service
      if (r.usd_per_eur !== pricing.usd_per_eur) rate = { ...rate, mode: 'manual', source: 'manual' }
      pricing = r
      return delay(pricingView(r))
    },
    previewPricing: (r) => delay(pricingView(r)),
    setRateMode: (mode) => {
      const now = new Date().toISOString()
      rate = mode === 'manual' ? { ...rate, mode } : { ...rate, mode, source: 'ECB', rate_date: '2026-10-13', last_checked: now, last_success: now, stale: false }
      if (mode === 'automatic') pricing = { ...pricing, usd_per_eur: 1.1188 }
      return delay(pricingView(pricing))
    },
    syncRate: () => {
      const now = new Date().toISOString()
      rate = { ...rate, last_checked: now, last_success: now, last_error: null, stale: false }
      return delay(pricingView(pricing))
    },
    resetPricing: () => {
      pricing = { ...pricing, default_margin_pct: 0, actions: {} }
      return delay(undefined)
    },
    financeCosts: (from, to, group) => {
      const rows = [
        { key: group === 'day' ? to : group === 'model' ? 'gpt-oss-120b' : group === 'user' ? 'admin@example.org' : group === 'service' ? 'rag' : 'chat_answer', calls: 42, actions: 30, cost_cents: 12.3456, cost_usd_cents: 13.8123, charge_cents: 16.0493 },
        { key: group === 'day' ? from : group === 'model' ? 'tts-1' : group === 'user' ? 'reader@example.org' : group === 'service' ? 'ingest' : 'output:audio', calls: 6, actions: 3, cost_cents: 40.5, cost_usd_cents: 45.31, charge_cents: 52.65 },
      ]
      return delay({ from, to, group, rows, total_cost_cents: 52.8456, total_cost_usd_cents: 59.1223, total_charge_cents: 68.6993 })
    },
    financeRevenue: (from, to) =>
      delay({ from, to, charged_cents: 68.6993, demo_charged_cents: 3.2, vouchers: { issued_paid_cents: 1000, issued_free_cents: 1500, redeemed_paid_cents: 500, redeemed_free_cents: 1000 }, outstanding_credit_cents: 1931.3 }),
    financeProfit: (from, to, group) => {
      const row = (period: string, k: number) => ({ period, charged_cents: 3400 * k, model_cost_cents: 2600 * k, infra_cost_cents: 900, profit_cents: 3400 * k - 2600 * k - 900, demo_charged_cents: 40, demo_cost_cents: 31 })
      const rows = group === 'month' ? [row('2026-09', 1), row('2026-10', 1.4)] : [row(from, 0.1), row(to, 0.12)]
      return delay({ from, to, group, usd_per_eur: infra.usd_per_eur, rows, total: null })
    },
    setVoucherPaid: (id, paid) => {
      const v = vouchers.find((x) => x.id === id)
      if (!v) return Promise.reject(new ApiError(404, 'unknown voucher'))
      Object.assign(v, { paid })
      return delay({ ...v })
    },
    listAccess: (limit) => delay(access.slice(0, limit)),
  }
}

export const admin: AdminApi = ADMIN_MOCK ? mockAdmin() : httpAdmin
