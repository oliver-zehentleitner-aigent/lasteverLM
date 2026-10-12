#!/usr/bin/env node
// Reachability check of a deployment through its ingress: the frontend's
// /healthz and the three API prefixes' /healthz. No browser, no login, no
// data written. Usage: node scripts/e2e.mjs https://host  (or make e2e URL=...)
const base = (process.argv[2] ?? process.env.URL ?? '').replace(/\/$/, '')
if (!base) {
  console.error('usage: node scripts/e2e.mjs <base url>')
  process.exit(2)
}
const checks = [
  ['web', '/healthz'],
  ['account', '/api/account/healthz'],
  ['ingest', '/api/ingest/healthz'],
  ['rag', '/api/rag/healthz'],
]
let failed = 0
for (const [name, path] of checks) {
  const url = base + path
  const started = Date.now()
  let line
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(10_000) })
    const text = (await res.text()).trim()
    let ok = res.ok
    try {
      ok = ok && JSON.parse(text).status === 'ok'
    } catch {
      ok = false
    }
    line = `${ok ? 'ok  ' : 'FAIL'} ${name.padEnd(8)} ${res.status} ${Date.now() - started}ms ${url}${ok ? '' : `  -> ${text.slice(0, 120).replace(/\s+/g, ' ')}`}`
    if (!ok) failed++
  } catch (e) {
    failed++
    line = `FAIL ${name.padEnd(8)} ---  ${Date.now() - started}ms ${url}  -> ${e instanceof Error ? e.message : String(e)}`
  }
  console.log(line)
}
process.exit(failed ? 1 : 0)
