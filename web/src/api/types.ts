// Mirrors the API contract in the parent's docs/architecture.md (v1.1).
// A change here is a change there first.

export type SourceKind = 'pdf' | 'text' | 'url' | 'image' | 'audio' | 'generated'
/** waiting_for_credit: added, and processed once the account has credit again */
export type SourceStatus = 'processing' | 'waiting_for_credit' | 'ready' | 'failed'
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
  /** where it opens without a bearer header: an image, PDF or text as a
   *  presigned GET of the original (valid one hour), a web page at its URL */
  preview_url?: string | null
  /** audio only: the upload as it came, presigned for an hour, when it was
   *  converted for transcription (then preview_url is the converted MP3);
   *  null when the file was transcribed as it came */
  original_url?: string | null
}

/** One upload or URL of the user, with the notebooks it is in. */
export interface LibraryEntry {
  id: string
  name: string
  /** `generated`: a document the user had made, usable as a source in
   *  another notebook; listed in the library's Outputs tab, not Sources */
  kind: SourceKind
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
  /** audio only: see Source.original_url */
  original_url?: string | null
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

/** The check on an answer or a document: how many claims it backed. */
export interface Check {
  method?: string
  threshold?: number
  supported: number
  unsupported: number
  unverified: number
}

/** A citing paragraph of an answer, `text` exactly as in the answer
 *  ([n] markers included), with the check's verdict. */
export type AnswerUnit = { text: string } & Claim

export interface Answer {
  message_id: string
  answer: string
  citations: Citation[]
  /** null for an answer without citations */
  units?: AnswerUnit[] | null
  check?: Check | null
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
  /** assistant messages with citations only; null otherwise and on older messages */
  units?: AnswerUnit[] | null
  check?: Check | null
}

// outputs (rag prefix)

export type OutputKind = 'report' | 'quiz' | 'table' | 'mindmap' | 'infographic' | 'audio' | 'decision'
export type OutputStatus = 'waiting' | 'processing' | 'ready' | 'failed'

export interface Output {
  id: string
  /** the notebook it was made in; null once that notebook is deleted (the
   *  document belongs to the user and stays in the library) */
  notebook_id: string | null
  /** that notebook's title when the document was made, kept after it is gone */
  origin_title?: string | null
  /** set only while it is in the trash */
  deleted_at?: string | null
  purge_at?: string | null
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
  /** how it was made and what each claim rests on; null for older outputs */
  provenance?: Provenance | null
}

/** How the check judged a claim: backed by its passages, not backed (no
 *  refs, a number not in the prompt, too little overlap), or not
 *  measurable (written in another language than its sources). A unit
 *  without `support` is no claim (a heading, a question). */
export type Support = 'supported' | 'unsupported' | 'unverified'

/** A claim's passages (numbers into `provenance.passages`) and verdict. */
export interface Claim {
  refs?: number[]
  support?: Support
}

/** A passage a document cites, numbered like a chat answer's citations.
 *  On the share page without chunk and source ids. */
export interface Passage {
  n: number
  chunk_id?: string
  source_id?: string
  source_name: string
  source_kind: SourceKind
  page: number | null
  chunk_index: number | null
  chunk_count: number | null
  similarity: number | null
  quote: string
}

/** `Output.provenance`, version 1: the generation log. */
export interface Provenance {
  version: number
  prompt_version: string
  model: string
  options: OutputOptions
  focus_query: string | null
  retrieval: {
    k: number
    floor: number
    candidates: { chunk_id?: string; source_id?: string; source_name: string; page: number | null; similarity: number; in_prompt: boolean }[]
  }
  passages: Passage[]
  usage: { llm?: { tokens_in: number; tokens_out: number }; embedding?: { tokens_in: number }; tts?: { seconds: number } }
  started_at: string
  finished_at: string
  check: Check & { method: string; threshold: number }
  /** the decision kind's two model calls */
  calls?: { role: 'decision' | 'evidence'; model: string; prompt_version: string; usage: Record<string, unknown>; started_at: string; finished_at: string; state?: { passages: number; chars: number } }[]
  /** an undecided decision: the evidence model's own sentence */
  llm_verdict_text?: string
}

/** How an audio document is spoken: one voice summarising, one voice
 *  telling it as a story, or two voices in conversation. */
export type AudioStyle = 'overview' | 'story' | 'conversation'

/** What a document is made with; which keys a kind takes comes from the spec. */
export interface OutputOptions {
  language?: string
  voice?: string
  speed?: number
  audio_style?: AudioStyle
  /** the second speaker, for a conversation only */
  audio_voice_2?: string
  /** decision: what is weighed, how it is answered, and the answers offered */
  question?: string
  decision_type?: DecisionType
  /** choice: 2–8 labels */
  choices?: string[]
  /** scale: 3–7 ordered labels, lowest first */
  levels?: string[]
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
  /** the decision kind's limits; absent from a service without it */
  decision?: {
    types: DecisionType[]
    default_type: DecisionType
    question_max_chars: number
    choices: { min: number; max: number }
    levels: { min: number; max: number }
  }
  kinds: Partial<Record<OutputKind, OutputOption[]>>
}

export type DecisionType = 'yes_no' | 'choice' | 'scale'

/** How the decision model's answer and the evidence relate: they point
 *  the same way, they do not, it cannot be told, or no supported evidence
 *  decides either way. */
export type Agreement = 'consistent' | 'conflicting' | 'unclear' | 'undecided'

/** A question weighed against the sources: the decision model's answer
 *  (all numbers 0–1, the scale's score a fractional index into its
 *  legend), the evidence on both sides as claims, and what the sources do
 *  not say. */
export interface DecisionContent {
  question: string
  decision_type: DecisionType
  model_answer:
    | { probability_yes: number; answer: 'yes' | 'no' }
    | { choice: string; distribution: Record<string, number>; confidence: number }
    | { level: string; score: number; legend: string[]; distribution: Record<string, number>; confidence: number }
  /** plain text, no markers */
  verdict_text: string
  /** choice and scale: the option the evidence argues for */
  llm_choice?: string | null
  evidence_for: ({ text: string } & Claim)[]
  evidence_against: ({ text: string } & Claim)[]
  gaps: string[]
  agreement: Agreement
  agreement_note?: string
}

/** `GET /shared/{token}`: the document without ids, read-only. The service
 *  returns kind, title, content, created_at and options (language, voice
 *  and speed for the line under the title); a shared document is always
 *  ready, so status and error are not part of the shape. */
export type SharedOutput = Pick<Output, 'kind' | 'title' | 'content' | 'created_at' | 'options' | 'provenance'>

export interface ReportContent {
  /** with [n] markers into `provenance.passages`, like a chat answer */
  markdown: string
  /** one per paragraph that is not a heading, `text` exactly as in the markdown */
  units?: ({ text: string } & Claim)[]
}
export interface QuizQuestion extends Claim {
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
  /** one per row, same index: what the row rests on; absent on older tables */
  row_refs?: Claim[]
}
/** `refs` on every node with provenance, `support` once checked (the root
 *  has none unless it cites) */
export interface MindmapNode extends Claim {
  label: string
  children?: MindmapNode[]
}
export interface MindmapContent {
  root: MindmapNode
}
export interface InfographicContent {
  headline: string
  facts: ({ label: string; value: string } & Claim)[]
  sections: ({ title: string; text: string } & Claim)[]
}
export interface AudioContent {
  url: string
  /** what is said, turn by turn: `narrator` for an overview or a story (a
   *  turn per paragraph), `interviewer` and `expert` for a conversation;
   *  absent on documents made before transcripts */
  transcript?: ({ speaker: string; text: string } & Claim)[]
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

/** user: the app only; viewer: reads the admin panel; admin: everything */
export type UserRole = 'user' | 'viewer' | 'admin'

export interface User {
  id: string
  email: string
  /** equals role === 'admin' */
  is_admin: boolean
  /** absent from an account service that predates roles */
  role?: UserRole
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
  /** a user from one of these (also allowed to sign in) starts as viewer;
   *  absent from an account service that predates roles */
  viewer_domains?: string[]
}

/** domain and address: who may sign in; viewer: domains whose new users are viewers */
export type AllowKind = 'domain' | 'address' | 'viewer'

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
  /** waiting_for_credit: jobs held until their owner has credit; absent from an older ingest */
  jobs: { pending: number; running: number; failed: number; waiting_for_credit?: number }
  chunks: number
  /** bytes in object storage, for sources uploaded since the size is stored */
  source_bytes: number
}

export interface RagStats {
  notebooks: { total: number }
  messages: { total: number; last_24h: number }
  outputs: { by_kind: Partial<Record<OutputKind, number>>; by_status: Record<OutputStatus, number> }
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
  /** a kind with no sources that day, or newer than the service, is absent */
  by_kind: Partial<Record<Exclude<SourceKind, 'generated'>, number>>
  /** of that day's sources, the ones that are failed now */
  failed: number
}

export interface RagDay {
  day: string
  messages: number
  outputs: number
  outputs_by_kind: Partial<Record<OutputKind, number>>
}

/** `GET /api/account/admin/system`: what runs where. `cluster: false` (a
 *  local run) comes with empty pods and deployments. */
/** The external services the diagram draws. */
export type Dependency = 'postgres' | 'storage' | 'inference'

export interface SystemInfo {
  version: string
  commit: string
  cluster: boolean
  services: {
    name: 'account' | 'ingest' | 'rag'
    version: string | null
    commit: string | null
    healthy: boolean
    /** what the service's healthz says about what it uses; null or absent until core reports it */
    dependencies?: Partial<Record<Dependency, 'ok' | 'down'>> | null
  }[]
  pods: {
    name: string
    service: string
    image_tag: string | null
    ready: boolean
    restarts: number
    node: string | null
    started_at: string | null
    /** a container's waiting or terminated reason (CrashLoopBackOff, Error, OOMKilled, …); absent when not reported */
    reason?: string | null
  }[]
  deployments: {
    name: string
    replicas: number
    ready: number
    updated: number
    /** a rollout is under way (Progressing true, not yet NewReplicaSetAvailable); null or absent when not reported */
    progressing?: boolean | null
  }[]
}

/** A service's public `/healthz`; version and commit are "unknown" when unset. */
export interface Health {
  status: string
  version?: string
  commit?: string
}
