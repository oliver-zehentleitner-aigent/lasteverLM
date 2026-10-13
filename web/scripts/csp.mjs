#!/usr/bin/env node
// Writes the nginx Content-Security-Policy line for the built app, so the
// hash of the inline theme script in index.html is derived from the build
// and cannot drift from it. Run in the image build after `vite build`:
//   node scripts/csp.mjs dist/index.html <off|report|enforce> [media-src] > csp.conf
// (API_BASE_URL from the environment adds the API's origin to connect-src)
// off      only frame-ancestors (the policy before this switch existed)
// report   the full policy as Content-Security-Policy-Report-Only, so a
//          browser lists what it would block and blocks nothing; the
//          frame-ancestors line stays enforced
// enforce  the full policy, enforced
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

export const MODES = ['off', 'report', 'enforce']

/** sha256 sources for every inline script (one without src) of a page. */
export function inlineScriptHashes(html) {
  const hashes = []
  for (const m of html.matchAll(/<script(\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
    if (/\ssrc=/.test(m[1] ?? '')) continue
    hashes.push(`'sha256-${createHash('sha256').update(m[2], 'utf8').digest('base64')}'`)
  }
  return hashes
}

/** The full policy. Styles allow inline because markmap writes a <style>
 *  element and style attributes; images and audio come from presigned
 *  object-storage URLs, hence the media sources. frame-ancestors is left
 *  out of a report-only policy, where browsers ignore it with a warning. */
export function policy(hashes, mediaSrc = 'https:', { frameAncestors = true, apiOrigin = '' } = {}) {
  const directives = [
    "default-src 'self'",
    `script-src 'self' ${hashes.join(' ')}`.trim(),
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${mediaSrc}`,
    `media-src 'self' blob: ${mediaSrc}`,
    `connect-src 'self' ${apiOrigin}`.trim(),
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
  ]
  if (frameAncestors) directives.push("frame-ancestors 'none'")
  return directives.join('; ')
}

/** The nginx lines for a mode. */
export function nginxLines(mode, html, mediaSrc, apiBaseUrl = '') {
  if (!MODES.includes(mode)) throw new Error(`CSP mode must be one of ${MODES.join(', ')}, not "${mode}"`)
  const frame = `add_header Content-Security-Policy "frame-ancestors 'none'" always;`
  if (mode === 'off') return frame + '\n'
  const hashes = inlineScriptHashes(html)
  // an API on another origin (API_BASE_URL set at build) has to be reachable
  const apiOrigin = apiBaseUrl ? new URL(apiBaseUrl).origin : ''
  if (mode === 'report') {
    return `${frame}\nadd_header Content-Security-Policy-Report-Only "${policy(hashes, mediaSrc, { frameAncestors: false, apiOrigin })}" always;\n`
  }
  return `add_header Content-Security-Policy "${policy(hashes, mediaSrc, { apiOrigin })}" always;\n`
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const [file, mode = 'off', mediaSrc = 'https:'] = process.argv.slice(2)
  if (!file) {
    console.error('usage: node scripts/csp.mjs <index.html> <off|report|enforce> [media-src]')
    process.exit(2)
  }
  process.stdout.write(nginxLines(mode, readFileSync(file, 'utf8'), mediaSrc, process.env.API_BASE_URL ?? ''))
}
