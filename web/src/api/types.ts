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
  /** how a PDF was read; null for other kinds */
  capture?: 'auto' | 'text' | 'vision' | null
  /** one of the example sources a new account starts with */
  demo?: boolean
  /** images only: a presigned picture of it, valid one hour */
  preview_url?: string | null
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
  /** how a PDF was read; null for other kinds */
  capture?: 'auto' | 'text' | 'vision' | null
  /** one of the example sources a new account starts with */
  demo?: boolean
  /** images only: a presigned picture of it, valid one hour */
  preview_url?: string | null
  created_at: string
  notebooks: { id: string; title: string; source_id: string }[]
}

/** A deleted library entry, kept until `purge_at` (the user's trash days). */
export interface TrashEntry extends Omit<LibraryEntry, 'notebooks'> {
  deleted_at: string
  purge_at: string
}

export interface Citation {
  n: number
  source_id: string
  source_name: string
  /** lets a citation into a generated document open that output's tab */
  source_kind: SourceKind
  chunk_id: string
  page: number | null
  /** the full verbatim chunk text (trimmed to 300 characters before) */
  quote: string
  /** cosine similarity to the question, 3 decimals; null on older messages */
  similarity?: number | null
  /** 0-based position among the source's chunks; null on older messages */
  chunk_index?: number | null
  chunk_count?: number | null
}

/** `GET /api/rag/chunks/{id}`: one chunk with its position, for citations
 *  written before they carried it. */
export interface Chunk {
  chunk_id: string
  source_id: string
  source_name: string
  source_kind: SourceKind
  page: number | null
  chunk_index: number
  chunk_count: number
  text: string
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
  /** the options it was made with, defaults filled in; {} for older outputs */
  options?: OutputOptions
}

/** What a document is made with; which keys a kind takes comes from the spec. */
export interface OutputOptions {
  language?: string
  voice?: string
  speed?: number
  /** in a response only: the source ids the document was made from,
   *  absent when all sources were used (the request sends `source_ids`) */
  sources?: string[]
}

export type OutputOption = Exclude<keyof OutputOptions, 'sources'>

/** `GET /api/rag/outputs/options`: the choices per kind. */
export interface OutputOptionsSpec {
  languages: { code: string; label: string }[]
  audio: {
    voices: { id: string; label: string; gender: 'male' | 'female'; language: string }[]
    default_voice: string
    speed: { min: number; max: number; step: number; default: number }
  }
  kinds: Partial<Record<OutputKind, OutputOption[]>>
}

/** `GET /shared/{token}`: the document without ids, read-only. The service
 *  returns kind, title, content, created_at and options (language, voice
 *  and speed for the line under the title); a shared document is always
 *  ready, so status and error are not part of the shape. */
export type SharedOutput = Pick<Output, 'kind' | 'title' | 'content' | 'created_at' | 'options'>

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

/** null means not set: the web's default UI language, the sources'
 *  language for documents, the platform's default voice. */
export interface Preferences {
  ui_language: 'de' | 'en' | null
  output_language: string | null
  audio_voice: string | null
  /** days a deleted library entry stays in the trash, 1–365; null is 14 */
  trash_days?: number | null
  /** how PDFs are read by default; null is auto */
  pdf_capture?: 'auto' | 'text' | 'vision' | null
  /** light, dark, or following the system; null is system */
  theme?: 'system' | 'light' | 'dark' | null
}

export interface User {
  id: string
  email: string
  is_admin: boolean
  balance_cents: number
  created_at: string
  /** absent from services that predate preferences */
  preferences?: Preferences
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
  /** the key: an IPv4 address or an IPv6 /64 prefix, shown as is */
  ip: string
  blocked_until: string
  strikes: number
  updated_at: string
}

export interface Ban {
  /** the key: an IPv4 address or an IPv6 /64 prefix, shown as is */
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

// admin statistics: daily series over the last N UTC days, oldest first,
// today last, every day present with zeros

export interface AccountDay {
  day: string
  logins: number
  visits: number
  usage_cost_cents: number
  credits_granted_cents: number
}

export interface AccountUsage {
  /** cost descending */
  by_model: { model: string; kind: 'llm' | 'embedding' | 'tts'; calls: number; cost_cents: number }[]
  /** top ten by usage, descending */
  top_users: { email: string; usage_cents: number; balance_cents: number }[]
}

export interface IngestDay {
  day: string
  /** library sources created that day; generated documents not counted */
  sources_created: number
  by_kind: Record<Exclude<SourceKind, 'generated'>, number>
  /** of that day's sources, the ones that are failed now */
  failed: number
}

export interface RagDay {
  day: string
  messages: number
  outputs: number
  outputs_by_kind: Record<OutputKind, number>
}

/** `GET /api/account/admin/system`: what runs where. `cluster: false` (a
 *  local run) comes with empty pods and deployments. */
export interface SystemInfo {
  version: string
  commit: string
  cluster: boolean
  services: { name: 'account' | 'ingest' | 'rag'; version: string | null; commit: string | null; healthy: boolean }[]
  pods: { name: string; service: string; image_tag: string | null; ready: boolean; restarts: number; node: string | null; started_at: string | null }[]
  deployments: { name: string; replicas: number; ready: number; updated: number }[]
}

/** A service's public `/healthz`; version and commit are "unknown" when unset. */
export interface Health {
  status: string
  version?: string
  commit?: string
}
