import { getToken } from './token'

export class ApiError extends Error {
  readonly status: number
  /** the service's stable machine-readable `code`, when it sends one */
  readonly code: string | null
  constructor(status: number, message: string, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** 401 and 402 are application states, not per-call errors: the token is
 *  gone, or the credit is. The app listens here once instead of every pane
 *  checking status codes. The ApiError is still thrown to the caller. */
export const apiEvents = new EventTarget()
export const UNAUTHORIZED = 'unauthorized'
export const PAYMENT_REQUIRED = 'payment-required'

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE' | 'PUT'
  json?: unknown
  form?: FormData
  /** Skip the Bearer header, for the login endpoints and the share page. */
  anonymous?: boolean
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
    throw new ApiError(0, NETWORK_MESSAGE)
  }

  if (res.status === 401) apiEvents.dispatchEvent(new Event(UNAUTHORIZED))
  if (res.status === 402) apiEvents.dispatchEvent(new Event(PAYMENT_REQUIRED))

  if (res.status === 204) return { status: 204, body: undefined as T }

  const text = await res.text()
  if (!res.ok) throw new ApiError(res.status, failureMessage(res.status, text), serviceCode(text))

  if (!text) return { status: res.status, body: undefined as T }
  try {
    return { status: res.status, body: JSON.parse(text) as T }
  } catch {
    throw new ApiError(res.status, 'The server answered with something that is not JSON.')
  }
}

export const NETWORK_MESSAGE = 'Cannot reach the server. Check your connection, or try again in a moment.'

/** What the user reads for a failed response. Pure, so the mapping is
 *  tested; the UI shows this string and nothing else. */
export function failureMessage(status: number, bodyText: string): string {
  const fromService = serviceError(bodyText)
  if (fromService) return fromService
  const described = STATUS_TEXT[status]
  return described ? `${described} (HTTP ${status})` : `The server answered with HTTP ${status}.`
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
const STATUS_TEXT: Record<number, string> = {
  400: 'The request was not understood',
  401: 'You are signed out',
  402: 'Your credit is used up',
  403: 'This needs admin rights',
  404: 'Not found, or not yours',
  409: 'Not ready yet',
  413: 'The file is too large for the server',
  415: 'This file type is not supported',
  422: 'The request was rejected',
  429: 'Too many requests, slow down',
  500: 'The server hit an error',
  501: 'This source type is not supported yet',
  502: 'The service is not reachable, it may still be starting',
  503: 'The service is unavailable, it may still be starting',
  504: 'The service took too long to answer',
}
