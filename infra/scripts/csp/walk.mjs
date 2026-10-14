// Walks the built web app in headless Chromium and reports every CSP violation.
// Runs inside the Playwright image (scripts/web-csp-check.sh). The app comes from
// WEB_URL (the web image); /api and /shared are fetched from API_URL (the live
// deployment) through page.route, so the page sees one origin as in production.
// DEMO_TOKEN signs in; it is read from the environment and never printed.
// Every request to API_URL waits for a slot: WALK_RPS per second (default 1), well
// under core's per-address rate limit (120 a minute), which a walk shares with
// everything else leaving the same address.
import { chromium } from 'playwright'

const WEB = process.env.WEB_URL
const API = process.env.API_URL
const TOKEN = process.env.DEMO_TOKEN
if (!WEB || !API || !TOKEN) {
  console.error('WEB_URL, API_URL and DEMO_TOKEN are required')
  process.exit(2)
}

const RPS = Number(process.env.WALK_RPS || 1)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let nextSlot = 0
let busy = 0 // requests to the API waiting for a slot or in flight
let sent = 0
const throttled = async (fn) => {
  busy++
  try {
    const now = Date.now()
    const at = Math.max(now, nextSlot)
    nextSlot = at + 1000 / RPS
    if (at > now) await sleep(at - now)
    sent++
    return await fn()
  } finally {
    busy--
  }
}
const started = Date.now()

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1400, height: 900 } })
const page = await context.newPage()

// Same-origin API: requests to the web origin's /api and /shared go to the live API.
await page.route(/\/(api|shared)\//, async (route) => {
  const url = new URL(route.request().url())
  if (url.origin !== new URL(WEB).origin) return route.continue()
  try {
    const response = await throttled(() => route.fetch({ url: API + url.pathname + url.search }))
    await route.fulfill({ response })
  } catch {
    // the page navigated away while the request waited for its slot
    await route.abort().catch(() => {})
  }
})

// Violations, from the DOM event (enforced and report-only alike) and the console.
const violations = new Map()
const add = (key) => violations.set(key, (violations.get(key) ?? 0) + 1)
await context.exposeBinding('__cspViolation', (_src, v) => add(`${v.directive} ${v.blocked}`))
await context.addInitScript(() => {
  document.addEventListener('securitypolicyviolation', (e) =>
    window.__cspViolation({ directive: e.effectiveDirective, blocked: e.blockedURI || '(inline)' }),
  )
})
const consoleErrors = new Map()
page.on('console', (m) => {
  if (m.type() !== 'error') return
  const text = m.text().replaceAll(TOKEN, '<token>').slice(0, 240)
  consoleErrors.set(text, (consoleErrors.get(text) ?? 0) + 1)
})
page.on('pageerror', (e) => consoleErrors.set('pageerror: ' + e.message.slice(0, 200), 1))
const failed = new Map()
// Origins the page loads from directly (not through the API route): storage, fonts, …
const origins = new Map()
const track = async (r) => {
  const origin = new URL(r.url()).origin
  if (origin === new URL(WEB).origin) return
  const resp = await r.response()
  const key = `${r.resourceType()} ${origin} ${resp ? resp.status() : '-'}`
  origins.set(key, (origins.get(key) ?? 0) + 1)
}
page.on('requestfinished', track)
page.on('requestfailed', track)
page.on('response', (r) => {
  if (r.status() < 400) return
  const key = `${r.status()} ${new URL(r.url()).pathname.replace(/[0-9a-f-]{36}/g, '<id>')}`
  failed.set(key, (failed.get(key) ?? 0) + 1)
})

// Plays the first <audio> for a moment; reports its origin and whether it got data.
const playAudio = async () => {
  const a = await page.$('audio')
  if (!a) return 'no <audio> element'
  const result = await a.evaluate(async (el) => {
    try {
      await el.play()
      await new Promise((r) => setTimeout(r, 1500))
      el.pause()
    } catch (e) {
      return { error: String(e).slice(0, 120) }
    }
    return { origin: new URL(el.currentSrc).origin, readyState: el.readyState, played: el.currentTime > 0 }
  })
  return JSON.stringify(result)
}

const visited = []
const step = async (label, fn) => {
  try {
    await fn()
    visited.push(label)
  } catch (e) {
    visited.push(`${label} (failed: ${e.message.split('\n')[0].slice(0, 120)})`)
  }
}
// Waits ms, then until the page's API requests have drained (at most 60 s more).
const settle = async (ms = 2500) => {
  await page.waitForTimeout(ms)
  for (let i = 0; busy > 0 && i < 120; i++) await page.waitForTimeout(500)
}
const api = async (path) => {
  const r = await throttled(() => fetch(API + path, { headers: { Authorization: 'Bearer ' + TOKEN } }))
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
  return r.json()
}

const cspHeader = async (path) => {
  const r = await fetch(WEB + path)
  return r.headers.get('content-security-policy-report-only') ? 'report-only'
    : r.headers.get('content-security-policy') ? 'enforced' : 'none'
}
for (let i = 0; ; i++) {
  try {
    await fetch(WEB + '/healthz')
    break
  } catch (e) {
    if (i === 30) throw e
    await new Promise((r) => setTimeout(r, 500))
  }
}
console.log('policy on /:', await cspHeader('/'))

await page.goto(WEB + '/')
await page.evaluate((t) => localStorage.setItem('lasteverlm.token', t), TOKEN)

// Canary: an inline script the policy must report. Without it, "0 violations"
// could also mean the listener never ran.
await page.evaluate(() => {
  const s = document.createElement('script')
  s.textContent = 'window.__cspCanary = 1'
  document.head.append(s)
})
await settle(500)
const canary = violations.size > 0
violations.clear()
consoleErrors.clear() // the canary's own console message
console.log('canary (inline script) reported:', canary)

const notebooks = await api('/api/ingest/notebooks')
const shares = new Map() // kind -> share token, one shared page per output kind
let judged = null // one output a judge has read, opened with its judge panel
for (const nb of notebooks.slice(0, Number(process.env.MAX_NOTEBOOKS ?? 6))) {
  const outputs = await api(`/api/rag/notebooks/${nb.id}/outputs`)
  const ready = outputs.filter((o) => o.status === 'ready')
  for (const o of outputs) if (o.share_token && o.status === 'ready' && !shares.has(o.kind)) shares.set(o.kind, o.share_token)
  // judged while made (provenance.judge) or afterwards (provenance.judgements)
  if (!judged) judged = ready.find((o) => o.provenance?.judge || o.provenance?.judgements?.length) ?? null
  await page.evaluate((id) => localStorage.setItem('lasteverlm.notebook', id), nb.id)
  await step(`notebook ${nb.id.slice(0, 8)}`, async () => {
    await page.goto(WEB + '/')
    await settle()
  })
  for (const kind of [...new Set(ready.map((o) => o.kind))]) {
    const o = ready.find((x) => x.kind === kind)
    await step(`  output ${kind}`, async () => {
      await page.click(`#output-${o.id} .out-row`, { timeout: 4000 })
      await settle(kind === 'mindmap' || kind === 'audio' ? 3500 : 1500)
      if (kind === 'audio') console.log('  audio in viewer:', await playAudio())
    })
  }
  if (judged && ready.includes(judged)) {
    await step(`  output ${judged.kind} with judge panel`, async () => {
      await page.click(`#output-${judged.id} .out-row`, { timeout: 4000 })
      await settle(1500)
      await page.click('.badge.judge', { timeout: 4000 })
      await settle(1000)
      for (const d of await page.$$('details.out-sources, details.how-made')) await d.evaluate((el) => (el.open = true))
      await settle(1000)
    })
  }
}
if (!judged) visited.push('output with judge panel (no judged output found)')
const adminPages = ['/admin', '/admin/users', '/admin/access', '/admin/security', '/admin/visits', '/admin/mail', '/admin/system']
const financePages = ['/admin/finance', '/admin/finance/prices', '/admin/finance/revenue', '/admin/finance/infrastructure', '/admin/finance/vouchers']
for (const path of ['/library', '/settings', ...adminPages, ...financePages]) {
  await step(path, async () => {
    await page.goto(WEB + path)
    await settle()
  })
}
for (const [kind, token] of shares) {
  await step(`/s/<share> ${kind}`, async () => {
    await page.goto(WEB + '/s/' + token)
    await settle(3000)
    if (kind === 'audio') console.log('  audio on share page:', await playAudio())
  })
}
if (!shares.size) visited.push('/s/<share> (no shared output found)')
for (const theme of ['toggle 1', 'toggle 2']) {
  await step(`theme ${theme}`, async () => {
    await page.goto(WEB + '/')
    await settle(1500)
    await page.click('.theme-toggle', { timeout: 3000 })
    await settle(1000)
  })
}
await browser.close()

const seconds = (Date.now() - started) / 1000
console.log(`\nAPI requests: ${sent} in ${Math.round(seconds)} s (${Math.round((sent / seconds) * 60)} a minute, WALK_RPS ${RPS})`)
console.log('\nvisited:')
for (const v of visited) console.log('  ' + v)
console.log(`\nCSP violations (distinct): ${violations.size}`)
for (const [k, n] of violations) console.log(`  ${n}x ${k}`)
console.log(`\nconsole errors (distinct): ${consoleErrors.size}`)
for (const [k, n] of consoleErrors) console.log(`  ${n}x ${k}`)
console.log(`\nother origins loaded (type origin status): ${origins.size}`)
for (const [k, n] of origins) console.log(`  ${n}x ${k}`)
console.log(`\nfailed responses (distinct): ${failed.size}`)
for (const [k, n] of failed) console.log(`  ${n}x ${k}`)
if (!canary) {
  console.error('the canary violation was not reported: no policy on the page, or the listener did not run')
  process.exit(2)
}
process.exit(violations.size ? 1 : 0)
