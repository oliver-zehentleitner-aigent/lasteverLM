import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import { inlineScriptHashes, nginxLines, policy } from './csp.mjs'

const body = "\n      try { document.documentElement.dataset.x = '1' } catch (e) {}\n    "
const html = `<head><script>${body}</script><script type="module" crossorigin src="/assets/index.js"></script></head>`
const hash = `'sha256-${createHash('sha256').update(body, 'utf8').digest('base64')}'`

describe('inlineScriptHashes', () => {
  it('hashes the inline script exactly as written and skips scripts with src', () => {
    expect(inlineScriptHashes(html)).toEqual([hash])
  })

  it('finds the closing tag in any case and with whitespace, and skips any src', () => {
    const odd = `<SCRIPT nonce="x">${body}</SCRIPT >\n<script type="module" SRC = "/a.js"></script><script\tsrc="/b.js"></script>`
    expect(inlineScriptHashes(odd)).toEqual([hash])
  })

  it('ends a script at a closing tag with junk in it, as browsers do', () => {
    expect(inlineScriptHashes(`<script>${body}</script\t\n bar>`)).toEqual([hash])
  })
})

describe('nginxLines', () => {
  it('keeps only frame-ancestors when off', () => {
    expect(nginxLines('off', html)).toBe(`add_header Content-Security-Policy "frame-ancestors 'none'" always;\n`)
  })

  it('reports the full policy without enforcing it, frame-ancestors still enforced', () => {
    const lines = nginxLines('report', html)
    expect(lines).toContain(`Content-Security-Policy "frame-ancestors 'none'"`)
    expect(lines).toContain(`Content-Security-Policy-Report-Only "${policy([hash], 'https:', { frameAncestors: false })}"`)
    expect(lines.split('\n')[1]).not.toContain('frame-ancestors')
  })

  it('enforces the full policy with the hash and the media sources', () => {
    const lines = nginxLines('enforce', html, 'https://ams1.vultrobjects.com')
    expect(lines).toContain(`script-src 'self' ${hash}`)
    expect(lines).toContain('media-src \'self\' blob: https://ams1.vultrobjects.com')
    expect(lines).toContain("frame-src 'self' https://ams1.vultrobjects.com")
    expect(lines).not.toContain('Report-Only')
    expect(lines).toContain("frame-ancestors 'none'")
  })

  it('lets the app reach an API on another origin', () => {
    expect(nginxLines('enforce', html, 'https:', 'https://api.example.org/base/')).toContain("connect-src 'self' https://api.example.org;")
    expect(nginxLines('enforce', html, 'https:', '')).toContain("connect-src 'self';")
  })

  it('refuses an unknown mode', () => {
    expect(() => nginxLines('on', html)).toThrow(/off, report, enforce/)
  })
})
