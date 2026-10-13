// Walks the built web app in headless Chromium and reports every CSP violation.
// Runs inside the Playwright image (scripts/web-csp-check.sh). The app comes from
// WEB_URL (the web image); /api and /shared are fetched from API_URL (the live
// deployment) through page.route, so the page sees one origin as in production.
// DEMO_TOKEN signs in; it is read from the environment and never printed.
import { chromium } from 'playwright'

const WEB = process.env.WEB_URL
const API = process.env.API_URL
const TOKEN = process.env.DEMO_TOKEN
if (!WEB || !API || !TOKEN) {
  console.error('WEB_URL, API_URL and DEMO_TOKEN are required')
  process.exit(2)
}

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1400, height: 900 } })
const page = await context.newPage()

// Same-origin API: requests to the web origin's /api and /shared go to the live API.
await page.route(/\/(api|shared)\//, async (route) => {
  const url = new URL(route.request().url())
  if (url.origin !== new URL(WEB).origin) return route.continue()
  const response = await route.fetch({ url: API + url.pathname + url.search })
  await route.fulfill({ response })
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
page.on('response', (r) => {
  if (r.status() < 400) return
  const key = `${r.status()} ${new URL(r.url()).pathname.replace(/[0-9a-f-]{36}/g, '<id>')}`
  failed.set(key, (failed.get(key) ?? 0) + 1)
})

const visited = []
const step = async (label, fn) => {
  try {
    await fn()
    visited.push(label)
  } catch (e) {
    visited.push(`${label} (failed: ${e.message.split('\n')[0].slice(0, 120)})`)
  }
}
const settle = (ms = 2500) => page.waitForTimeout(ms)
const api = async (path) => {
  const r = await fetch(API + path, { headers: { Authorization: 'Bearer ' + TOKEN } })
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
console.log('canary (inline script) reported:', canary)

const notebooks = await api('/api/ingest/notebooks')
let share = null
for (const nb of notebooks.slice(0, Number(process.env.MAX_NOTEBOOKS ?? 6))) {
  const outputs = await api(`/api/rag/notebooks/${nb.id}/outputs`)
  const ready = outputs.filter((o) => o.status === 'ready')
  for (const o of outputs) if (o.share_token && !share) share = o.share_token
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
      if (kind === 'audio') await page.$eval('audio', (a) => a.play()).catch(() => {})
    })
  }
}
for (const path of ['/library', '/settings', '/admin', '/admin/system', '/admin/stats']) {
  await step(path, async () => {
    await page.goto(WEB + path)
    await settle()
  })
}
if (share) {
  await step('/s/<share>', async () => {
    await page.goto(WEB + '/s/' + share)
    await settle(3000)
  })
} else {
  visited.push('/s/<share> (no shared output found)')
}
for (const theme of ['toggle 1', 'toggle 2']) {
  await step(`theme ${theme}`, async () => {
    await page.goto(WEB + '/')
    await settle(1500)
    await page.click('.theme-toggle', { timeout: 3000 })
    await settle(1000)
  })
}
await browser.close()

console.log('\nvisited:')
for (const v of visited) console.log('  ' + v)
console.log(`\nCSP violations (distinct): ${violations.size}`)
for (const [k, n] of violations) console.log(`  ${n}x ${k}`)
console.log(`\nconsole errors (distinct): ${consoleErrors.size}`)
for (const [k, n] of consoleErrors) console.log(`  ${n}x ${k}`)
console.log(`\nfailed responses (distinct): ${failed.size}`)
for (const [k, n] of failed) console.log(`  ${n}x ${k}`)
if (!canary) {
  console.error('the canary violation was not reported: no policy on the page, or the listener did not run')
  process.exit(2)
}
process.exit(violations.size ? 1 : 0)
