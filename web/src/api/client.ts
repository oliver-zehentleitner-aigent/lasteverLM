import { t, type MessageKey } from '../i18n'
import { formatCents } from '../lib/format'
import { getToken } from './token'

export class ApiError extends Error {
  readonly status: number
  /** the service's stable machine-readable `code`, when it sends one */
  readonly code: string | null
  /** the failed response's body as JSON, for the few calls whose error
   *  carries more than a sentence; null when it was not JSON */
  readonly body: unknown
  constructor(status: number, message: string, code: string | null = null, body: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.body = body
  }
}

/** 401 and 402 are application states, not per-call errors: the token is
 *  gone, or the credit is. The app listens here once instead of every pane
 *  checking status codes. The ApiError is still thrown to the caller. A
 *  402 is a CustomEvent: its detail is the sentence when the credit is
 *  there but does not cover the action (`credit_insufficient`), else null. */
export const apiEvents = new EventTarget()
export const UNAUTHORIZED = 'unauthorized'
export const PAYMENT_REQUIRED = 'payment-required'
export const OPEN_VOUCHER = 'open-voucher'

/** Opens the voucher dialog from anywhere ("redeem a voucher" next to a
 *  source waiting for credit); App listens, as for a 402. */
export function openVoucher(): void {
  apiEvents.dispatchEvent(new Event(OPEN_VOUCHER))
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE' | 'PUT' | 'PATCH'
  json?: unknown
  form?: FormData
  /** Skip the Bearer header, for the login endpoints and the share page. */
  anonymous?: boolean
  /** The body as plain text, not JSON (a source's stored text). */
  text?: boolean
}

/** One place for auth, error shape and JSON handling. Errors are thrown,
 *  never swallowed, and always carry a sentence a user can read: the
 *  service's {"error"} text when there is one, otherwise a description
 *  of the status (an HTML page from the ingress is never shown as is). */
export async function request<T>(url: string, opts: RequestOptions = {}): Promise<T> {
  return (await requestWithStatus<T>(url, opts)).body
}

/** `request` plus the success status, for the few calls where 200 and 202
 *  mean different things (a source that was already in the notebook). */
export async function requestWithStatus<T>(url: string, opts: RequestOptions = {}): Promise<{ status: number; body: T }> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token && !opts.anonymous) headers['Authorization'] = `Bearer ${token}`

  let body: BodyInit | undefined
  if (opts.form) {
    body = opts.form
  } else if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.json)
  }

  let res: Response
  try {
    res = await fetch(url, { method: opts.method ?? 'GET', headers, body })
  } catch {
    throw new ApiError(0, networkMessage())
  }

  if (res.status === 204) return { status: 204, body: undefined as T }

  const text = await res.text()
  if (res.status === 401) apiEvents.dispatchEvent(new Event(UNAUTHORIZED))
  if (res.status === 402) {
    const short = serviceCode(text) === 'credit_insufficient' ? failureMessage(402, text) : null
    apiEvents.dispatchEvent(new CustomEvent<string | null>(PAYMENT_REQUIRED, { detail: short }))
  }
  if (!res.ok) throw new ApiError(res.status, failureMessage(res.status, text), serviceCode(text), jsonOrNull(text))

  if (opts.text) return { status: res.status, body: text as T }
  if (!text) return { status: res.status, body: undefined as T }
  try {
    return { status: res.status, body: JSON.parse(text) as T }
  } catch {
    throw new ApiError(res.status, t('http.notJson'))
  }
}

export function networkMessage(): string {
  return t('http.network')
}

/** What the user reads for a failed response. Pure, so the mapping is
 *  tested; the UI shows this string and nothing else. */
export function failureMessage(status: number, bodyText: string): string {
  const code = serviceCode(bodyText)
  if (code === 'model_no_answer') return modelNoAnswer(bodyText)
  if (code === 'credit_insufficient') return creditShort(bodyText)
  // chart candidates proposed for another selection: rag refuses them on Create
  if (code === 'chart_out_of_scope') return t('chartOut.stale')
  const fromService = serviceError(bodyText)
  if (fromService) return fromService
  return STATUS_TEXT.has(status)
    ? t('http.status', { text: t(`http.${status}` as MessageKey), status })
    : t('http.unknown', { status })
}

/** The service's own `{"error": "<message>"}`, if the body is one. */
function serviceError(bodyText: string): string | null {
  if (!bodyText) return null
  try {
    const data: unknown = JSON.parse(bodyText)
    if (data && typeof data === 'object' && 'error' in data) {
      const e = (data as { error: unknown }).error
      if (typeof e === 'string' && e.trim()) return e
    }
  } catch {
    // not JSON: an HTML error page from the ingress, or plain text
  }
  return null
}

/** Why the model gave no answer, twice: rag's `cause`, one of a fixed
 *  set, in the user's language; an unknown one as "unknown". */
const MODEL_CAUSES = new Set(['timeout', 'rate_limited', 'provider_error', 'empty_answer', 'truncated_answer', 'unparseable_answer', 'no_audio', 'unknown'])

function modelNoAnswer(bodyText: string): string {
  const data = jsonOrNull(bodyText) as { cause?: unknown } | null
  const cause = typeof data?.cause === 'string' && MODEL_CAUSES.has(data.cause) ? data.cause : 'unknown'
  return t('http.modelNoAnswer', { cause: t(`http.modelCause.${cause}` as MessageKey) })
}

/** A 402 on output creation or a plan's confirm while there is credit,
 *  just not enough: what the action needs at most, what is available, and
 *  what work still running holds (only when it holds something). Euro
 *  cents, as floats. */
function creditShort(bodyText: string): string {
  const data = jsonOrNull(bodyText) as { needed_cents?: unknown; available_cents?: unknown; held_cents?: unknown } | null
  const cents = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)
  const needed = cents(data?.needed_cents)
  const available = cents(data?.available_cents)
  const held = cents(data?.held_cents)
  if (needed === null || available === null) return t('http.creditShortBare')
  const line = t('http.creditShort', { needed: formatCents(needed), available: formatCents(available) })
  return held !== null && held > 0 ? `${line} ${t('http.creditHeld', { held: formatCents(held) })}` : line
}

/** The `code` next to `error`, e.g. "not_allowed" on a refused sign-in. */
export function serviceCode(bodyText: string): string | null {
  try {
    const data: unknown = JSON.parse(bodyText)
    if (data && typeof data === 'object' && 'code' in data) {
      const c = (data as { code: unknown }).code
      if (typeof c === 'string' && c) return c
    }
  } catch {
    // no JSON body, no code
  }
  return null
}

/** Statuses the deployment produces without a JSON body, mostly from the
 *  ingress in front of the services, plus the contract's codes as a
 *  fallback when a service answers without a message. */
const STATUS_TEXT = new Set([400, 401, 402, 403, 404, 409, 413, 415, 422, 429, 500, 501, 502, 503, 504])

function jsonOrNull(text: string): unknown {
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}
