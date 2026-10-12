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

export interface Source {
  id: string
  notebook_id: string
  name: string
  kind: SourceKind
  status: SourceStatus
  error: string | null
  created_at: string
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

/** `GET /shared/{token}`: the same document without ids, read-only. */
export type SharedOutput = Pick<Output, 'kind' | 'title' | 'content' | 'status' | 'error' | 'created_at'>

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
}

export interface LoginEvent {
  user_id: string
  email: string
  at: string
}

/** Aggregated per day and path; the service stores no raw IP addresses. */
export interface VisitBucket {
  day: string
  path: string
  visits: number
  unique: number
}

export interface Smtp {
  host: string
  port: number
  username: string
  /** write-only: sent on PUT, never returned */
  password?: string
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
