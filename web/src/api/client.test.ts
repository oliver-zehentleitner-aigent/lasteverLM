import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, networkMessage, PAYMENT_REQUIRED, UNAUTHORIZED, apiEvents, failureMessage, request, serviceCode } from './client'

const html = '<html><head><title>502 Bad Gateway</title></head><body><center><h1>502 Bad Gateway</h1></center><hr><center>nginx</center></body></html>'

describe('failureMessage', () => {
  it('prefers the service message', () => {
    expect(failureMessage(409, '{"error":"output not ready"}')).toBe('output not ready')
    expect(failureMessage(415, '{"error":"unsupported media type: image/gif"}')).toBe('unsupported media type: image/gif')
    // too many sign-in links for one address: the service's sentence, as is
    const links = '5 sign-in links were sent to this address in the last hour. Use one of them, or try again later.'
    expect(failureMessage(429, JSON.stringify({ error: links, code: 'too_many_links' }))).toBe(links)
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
  it('says what an action needs against what there is, when the credit does not cover it', () => {
    const body = (extra: object) => JSON.stringify({ error: 'credit does not cover this', code: 'credit_insufficient', ...extra })
    expect(failureMessage(402, body({ needed_cents: 320, held_cents: 0, available_cents: 100 }))).toBe('This needs up to €3.20, you have €1.00.')
    expect(failureMessage(402, body({ needed_cents: 320.5, held_cents: 50, available_cents: 300 }))).toBe('This needs up to €3.21, you have €3.00. (€0.50 is held by work still running.)')
    // amounts missing: still no raw English
    expect(failureMessage(402, body({}))).toBe('Your credit does not cover this.')
    // the other 402s keep the service's sentence
    expect(failureMessage(402, '{"error":"credit exhausted"}')).toBe('credit exhausted')
  })
  it('asks to find tables or themes again when rag refuses their candidates', () => {
    expect(failureMessage(409, JSON.stringify({ error: 'x', code: 'candidate_out_of_scope' }))).toBe('The sources or the notes changed: find the proposals again for the current selection.')
  })
  it('asks to find charts again when rag refuses candidates from another selection', () => {
    const body = JSON.stringify({ error: 'charts: a candidate cites a source outside the selected sources; find charts again', code: 'chart_out_of_scope' })
    expect(failureMessage(409, body)).toBe('The sources or the notes changed: find charts again for the current selection.')
  })
  it("says why the model did not answer, in the user's language, from rag's cause", () => {
    const body = (cause: unknown) => JSON.stringify({ error: 'the model did not answer', code: 'model_no_answer', cause })
    expect(failureMessage(502, body('truncated_answer'))).toBe('The model did not answer, not on a second try either: the answer was cut off at its length limit. Try again in a moment.')
    expect(failureMessage(502, body('rate_limited'))).toContain('the provider is limiting requests right now')
    // a cause this build does not know, or none
    expect(failureMessage(502, body('quota'))).toContain('the reason is not known')
    expect(failureMessage(502, body(undefined))).toContain('the reason is not known')
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
  it("carries the short-credit sentence on the 402 event, null for an exhausted credit", async () => {
    const details: unknown[] = []
    const on = (e: Event) => details.push((e as CustomEvent).detail)
    apiEvents.addEventListener(PAYMENT_REQUIRED, on)
    stub(402, '{"error":"credit exhausted"}')
    await expect(request('/x')).rejects.toBeInstanceOf(ApiError)
    stub(402, JSON.stringify({ error: 'credit does not cover this', code: 'credit_insufficient', needed_cents: 320, held_cents: 0, available_cents: 100 }))
    await expect(request('/x')).rejects.toMatchObject({ code: 'credit_insufficient', message: 'This needs up to €3.20, you have €1.00.' })
    expect(details).toEqual([null, 'This needs up to €3.20, you have €1.00.'])
    apiEvents.removeEventListener(PAYMENT_REQUIRED, on)
  })
  it('turns a network failure into a readable message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(request('/x')).rejects.toMatchObject({ status: 0, message: networkMessage() })
  })
})

describe('serviceCode', () => {
  it('reads the code next to the error', () => {
    expect(serviceCode('{"error":"This address has no access to lasteverLM.","code":"not_allowed"}')).toBe('not_allowed')
  })

  it('is null without a code or without JSON', () => {
    expect(serviceCode('{"error":"forbidden"}')).toBeNull()
    expect(serviceCode('<html>403</html>')).toBeNull()
    expect(serviceCode('')).toBeNull()
  })
})
