import { getToken } from './token'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
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
  /** Skip the Bearer header, for the login endpoints. */
  anonymous?: boolean
}

/** One place for auth, error shape and JSON handling. Errors are thrown,
 *  never swallowed: the contract returns {"error": "<message>"} with a
 *  4xx/5xx status and the UI shows that message as is. */
export async function request<T>(url: string, opts: RequestOptions = {}): Promise<T> {
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

  const res = await fetch(url, { method: opts.method ?? 'GET', headers, body })

  if (res.status === 401) apiEvents.dispatchEvent(new Event(UNAUTHORIZED))
  if (res.status === 402) apiEvents.dispatchEvent(new Event(PAYMENT_REQUIRED))

  if (res.status === 204) return undefined as T

  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      if (!res.ok) throw new ApiError(res.status, text.slice(0, 200) || res.statusText)
      throw new ApiError(res.status, 'Response was not JSON')
    }
  }

  if (!res.ok) throw new ApiError(res.status, errorMessage(data) ?? res.statusText ?? `HTTP ${res.status}`)
  return data as T
}

function errorMessage(data: unknown): string | null {
  if (data && typeof data === 'object' && 'error' in data) {
    const e = (data as { error: unknown }).error
    if (typeof e === 'string') return e
  }
  return null
}
