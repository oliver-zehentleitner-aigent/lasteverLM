import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NETWORK_MESSAGE, PAYMENT_REQUIRED, UNAUTHORIZED, apiEvents, failureMessage, request } from './client'

const html = '<html><head><title>502 Bad Gateway</title></head><body><center><h1>502 Bad Gateway</h1></center><hr><center>nginx</center></body></html>'

describe('failureMessage', () => {
  it('prefers the service message', () => {
    expect(failureMessage(409, '{"error":"output not ready"}')).toBe('output not ready')
    expect(failureMessage(415, '{"error":"unsupported media type: image/gif"}')).toBe('unsupported media type: image/gif')
  })
  it('never shows an HTML error page, describes the status instead', () => {
    expect(failureMessage(502, html)).toBe('The service is not reachable, it may still be starting (HTTP 502)')
    expect(failureMessage(503, '')).toBe('The service is unavailable, it may still be starting (HTTP 503)')
    expect(failureMessage(413, '<html>413 Request Entity Too Large</html>')).toBe('The file is too large for the server (HTTP 413)')
  })
  it('covers the contract codes without a body and falls back to the bare status', () => {
    expect(failureMessage(501, '')).toBe('This source type is not supported yet (HTTP 501)')
    expect(failureMessage(402, '')).toBe('Your credit is used up (HTTP 402)')
    expect(failureMessage(418, '')).toBe('The server answered with HTTP 418.')
    expect(failureMessage(500, '{"error":"   "}')).toBe('The server hit an error (HTTP 500)')
  })
})

describe('request', () => {
  afterEach(() => vi.unstubAllGlobals())

  function stub(status: number, body: string, headers: Record<string, string> = {}) {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(status === 204 ? null : body, { status, headers })))
  }

  it('returns parsed JSON and undefined for 204', async () => {
    stub(200, '{"status":"ok"}')
    await expect(request('/x')).resolves.toEqual({ status: 'ok' })
    stub(204, '')
    await expect(request('/x')).resolves.toBeUndefined()
  })
  it('throws ApiError with the service message or the status description', async () => {
    stub(409, '{"error":"output not ready"}')
    await expect(request('/x')).rejects.toMatchObject({ name: 'ApiError', status: 409, message: 'output not ready' })
    stub(502, html, { 'content-type': 'text/html' })
    await expect(request('/x')).rejects.toMatchObject({ status: 502, message: expect.stringContaining('still be starting') })
  })
  it('raises the 401 and 402 events and still throws', async () => {
    const seen: string[] = []
    const on = (e: Event) => seen.push(e.type)
    apiEvents.addEventListener(UNAUTHORIZED, on)
    apiEvents.addEventListener(PAYMENT_REQUIRED, on)
    stub(401, '{"error":"invalid session token"}')
    await expect(request('/x')).rejects.toBeInstanceOf(ApiError)
    stub(402, '{"error":"credit exhausted"}')
    await expect(request('/x')).rejects.toMatchObject({ message: 'credit exhausted' })
    expect(seen).toEqual([UNAUTHORIZED, PAYMENT_REQUIRED])
    apiEvents.removeEventListener(UNAUTHORIZED, on)
    apiEvents.removeEventListener(PAYMENT_REQUIRED, on)
  })
  it('turns a network failure into a readable message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(request('/x')).rejects.toMatchObject({ status: 0, message: NETWORK_MESSAGE })
  })
})
