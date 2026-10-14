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
// The object storage origin the policy allows for images and audio; the library
// step checks that its loads went there.
const STORAGE = process.env.STORAGE_ORIGIN ?? ''
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
// Storage loads on /library: hovering an image's name loads its presigned preview,
// the play button of an audio source loads its presigned file. Each load must come
// from STORAGE and draw no violation.
const storageLoads = []
await step('/library storage loads', async () => {
  await page.goto(WEB + '/library')
  await settle()
  const before = violations.size
  const names = await page.$$('td.name .image-name')
  if (!names.length) storageLoads.push('image: no image entry in the library')
  else {
    await names[0].hover()
    const img = await page.waitForSelector('.image-preview img', { timeout: 10000 })
    await img.evaluate((el) => (el.complete ? null : new Promise((r) => { el.onload = el.onerror = r })))
    const r = await img.evaluate((el) => ({ origin: new URL(el.currentSrc || el.src).origin, width: el.naturalWidth }))
    storageLoads.push({ what: 'image preview', ...r, ok: r.origin === STORAGE && r.width > 0 })
    await page.mouse.move(0, 0)
  }
  const play = await page.$('td.row-actions button.icon.play')
  if (!play) storageLoads.push('audio: no audio source in the library')
  else {
    await play.click()
    await settle(1500)
    const r = await page.$eval('.audio-check audio', async (el) => {
      try {
        await el.play()
        await new Promise((res) => setTimeout(res, 1500))
        el.pause()
      } catch (e) {
        return { origin: new URL(el.currentSrc || el.src).origin, error: String(e).slice(0, 120) }
      }
      return { origin: new URL(el.currentSrc).origin, played: el.currentTime > 0 }
    })
    storageLoads.push({ what: 'audio source', ...r, ok: r.origin === STORAGE && r.played === true })
  }
  storageLoads.push({ what: 'violations during these loads', count: violations.size - before, ok: violations.size === before })
})
// A PDF source opened in its notebook's source tab: the original shows inline in a
// frame from its presigned URL, which frame-src has to allow.
await step('source tab with an inline PDF', async () => {
  let found = null
  for (const nb of notebooks) {
    const pdf = (await api(`/api/ingest/notebooks/${nb.id}/sources`)).find((x) => x.kind === 'pdf' && x.status === 'ready')
    if (pdf) {
      found = { nb, pdf }
      break
    }
  }
  if (!found) return storageLoads.push('pdf: no ready PDF source in a notebook')
  await page.evaluate((id) => localStorage.setItem('lasteverlm.notebook', id), found.nb.id)
  await page.goto(WEB + '/')
  await settle()
  const before = violations.size
  await page.click(`.sources li#source-${found.pdf.id} button.link.name`, { timeout: 5000 })
  const frame = await page.waitForSelector('.viewer-body iframe.source-frame', { timeout: 8000 }).catch(() => null)
  if (!frame) return storageLoads.push('pdf: this build shows no inline PDF frame')
  await settle(3000)
  const origin = await frame.evaluate((el) => new URL(el.src).origin)
  storageLoads.push({ what: 'inline PDF frame', origin, violations: violations.size - before, ok: origin === STORAGE && violations.size === before })
})
// The admin panel renders only for an admin or viewer; for anyone else /admin
// falls back to the notebook view, so a page counts as walked only with the panel.
let adminRendered = 0
for (const path of ['/library', '/settings', ...adminPages, ...financePages]) {
  await step(path, async () => {
    await page.goto(WEB + path)
    await settle()
    if (!path.startsWith('/admin')) return
    if (!(await page.$('main.admin'))) throw new Error('no admin panel: the token\'s user is not an admin or viewer')
    adminRendered++
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
console.log(`\nadmin panel rendered on ${adminRendered} of ${adminPages.length + financePages.length} admin pages`)
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
console.log(`\nstorage loads on /library (expected origin ${STORAGE || 'not set'}):`)
for (const l of storageLoads) console.log('  ' + (typeof l === 'string' ? l : JSON.stringify(l)))
const storageFailed = storageLoads.some((l) => typeof l === 'object' && !l.ok)
if (!canary) {
  console.error('the canary violation was not reported: no policy on the page, or the listener did not run')
  process.exit(2)
}
if (violations.size) process.exit(1)
if (storageFailed) {
  console.error('a storage load failed or came from another origin')
  process.exit(3)
}
process.exit(0)
