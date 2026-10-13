// Mirrors the API contract in the parent's docs/architecture.md (v1.1).
// A change here is a change there first.

export type SourceKind = 'pdf' | 'text' | 'url' | 'image' | 'generated'
export type SourceStatus = 'processing' | 'ready' | 'failed'
export type Role = 'user' | 'assistant'

export interface Notebook {
  id: string
  title: string
  created_at: string
}

/** A source in one notebook: a link to an entry of the user's library
 *  (`library_id`); name, kind, status and error are the entry's. */
export interface Source {
  id: string
  notebook_id: string
  name: string
  kind: SourceKind
  status: SourceStatus
  error: string | null
  created_at: string
  library_id?: string | null
}

/** One upload or URL of the user, with the notebooks it is in. */
export interface LibraryEntry {
  id: string
  name: string
  kind: Exclude<SourceKind, 'generated'>
  status: SourceStatus
  error: string | null
  /** null for URLs */
  size_bytes: number | null
  /** set only for URLs */
  url: string | null
  created_at: string
  notebooks: { id: string; title: string; source_id: string }[]
}

export interface Citation {
  n: number
  source_id: string
  source_name: string
  /** lets a citation into a generated document open that output's tab */
  source_kind: SourceKind
  chunk_id: string
  page: number | null
  quote: string
}

export interface Answer {
  message_id: string
  answer: string
  citations: Citation[]
}

/** One chat of a notebook, shown as a tab; messages belong to exactly one. */
export interface Conversation {
  id: string
  notebook_id: string
  title: string
  created_at: string
}

export interface Message {
  id: string
  role: Role
  content: string
  citations: Citation[] | null
  created_at: string
}

// outputs (rag prefix)

export type OutputKind = 'report' | 'quiz' | 'table' | 'mindmap' | 'infographic' | 'audio'
export type OutputStatus = 'waiting' | 'processing' | 'ready' | 'failed'

export interface Output {
  id: string
  notebook_id: string
  kind: OutputKind
  title: string
  /** one of the content shapes below, by kind; null until ready */
  content: unknown
  status: OutputStatus
  error: string | null
  share_token: string | null
  /** the `generated` source rag made from this document once it was ready; null before */
  source_id: string | null
  created_at: string
}

/** `GET /shared/{token}`: the document without ids, read-only. The service
 *  returns kind, title, content and created_at only; a shared document is
 *  always ready, so status and error are not part of the shape. */
export type SharedOutput = Pick<Output, 'kind' | 'title' | 'content' | 'created_at'>

export interface ReportContent {
  markdown: string
}
export interface QuizQuestion {
  question: string
  options: string[]
  /** the correct option, as text or as index */
  answer: string | number
  explanation: string
}
export interface QuizContent {
  questions: QuizQuestion[]
}
export interface TableContent {
  columns: string[]
  rows: (string | number | null)[][]
}
export interface MindmapNode {
  label: string
  children?: MindmapNode[]
}
export interface MindmapContent {
  root: MindmapNode
}
export interface InfographicContent {
  headline: string
  facts: { label: string; value: string }[]
  sections: { title: string; text: string }[]
}
export interface AudioContent {
  url: string
}

// account prefix

export interface User {
  id: string
  email: string
  is_admin: boolean
  balance_cents: number
  created_at: string
}

export interface AdminUser extends User {
  last_login_at: string | null
  usage_cents: number
  /** the user's ledger sum: credit granted by seed and redeemed vouchers */
  granted_cents: number
}

export interface LoginEvent {
  user_id: string
  email: string
  at: string
}

/** One sign-in link request, allowed or refused by the allowlist; kept 30 days. */
export interface LoginAttempt {
  at: string
  email: string
  ip: string
  outcome: 'allowed' | 'refused'
}

/** Aggregated per day and path; the service stores no raw IP addresses. */
export interface VisitBucket {
  day: string
  path: string
  visits: number
  unique: number
}

/** SMTP as configured in the deployment's environment, read-only; the
 *  password is never returned. An empty `host` means not configured. */
export interface Smtp {
  host: string
  port: number
  username: string
  from_address: string
  starttls: boolean
}

// rate limiting and blocking: the admin view on core's middleware

export interface Block {
  ip: string
  blocked_until: string
  strikes: number
  updated_at: string
}

export interface Ban {
  ip: string
  reason: string
  created_at: string
  lifted_at: string | null
}

/** Raw access log; the one place a full IP address is shown, admin only. */
export interface AccessEntry {
  at: string
  ip: string
  method: string
  path: string
  status: number
  user_id: string | null
  service: 'account' | 'ingest' | 'rag'
}

/** Who may sign in besides the configured admins: listed addresses and
 *  addresses at a listed domain. Both empty means only the admins. */
export interface Allowlist {
  allowed_domains: string[]
  allowed_addresses: string[]
}

export type AllowKind = 'domain' | 'address'

// admin overview: one stats endpoint per service, every key always present

export interface AccountStats {
  users: number
  logins_24h: number
  vouchers: { issued: number; redeemed: number; open: number }
  credits_granted_cents: number
  usage_cost_cents: { total: number; last_24h: number }
  blocks_active: number
  bans_active: number
}

export interface IngestStats {
  sources: { processing: number; ready: number; failed: number }
  jobs: { pending: number; running: number; failed: number }
  chunks: number
  /** bytes in object storage, for sources uploaded since the size is stored */
  source_bytes: number
}

export interface RagStats {
  notebooks: { total: number }
  messages: { total: number; last_24h: number }
  outputs: { by_kind: Record<OutputKind, number>; by_status: Record<OutputStatus, number> }
  jobs: { pending: number; running: number; failed: number }
  shared: { outputs: number }
}

/** One voucher as listed for admins; the code is stored hashed and never returned. */
export interface Voucher {
  id: string
  amount_cents: number
  created_by: string
  created_at: string
  redeemed_by: string | null
  redeemed_at: string | null
  status: 'open' | 'redeemed'
}

/** The rate-limit rule in force for every service. The first four are
 *  editable at run time; `ban_max_days` and `retention_days` come from the
 *  environment only. */
export interface RateLimitRules {
  per_minute: number
  block_minutes: number
  ban_after_strikes: number
  strike_window_hours: number
  ban_max_days: number
  retention_days: number
}

export type RateLimitUpdate = Pick<RateLimitRules, 'per_minute' | 'block_minutes' | 'ban_after_strikes' | 'strike_window_hours'>
