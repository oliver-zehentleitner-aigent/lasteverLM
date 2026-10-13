import { describe, expect, it } from 'vitest'
import { openTarget } from './openEntry'

describe('openTarget', () => {
  it('opens a web page at its address', () => {
    expect(openTarget({ kind: 'url', url: 'https://en.wikipedia.org/wiki/Danube', preview_url: null })).toBe('https://en.wikipedia.org/wiki/Danube')
  })

  it('opens an upload through its presigned preview', () => {
    const signed = 'https://ams1.vultrobjects.com/bucket/key?X-Amz-Signature=abc'
    expect(openTarget({ kind: 'pdf', url: null, preview_url: signed })).toBe(signed)
    expect(openTarget({ kind: 'image', url: null, preview_url: signed })).toBe(signed)
  })

  it('has nothing to open without a preview', () => {
    expect(openTarget({ kind: 'text', url: null, preview_url: null })).toBeNull()
    expect(openTarget({ kind: 'pdf', url: null })).toBeNull()
  })

  it('never links a script or data address', () => {
    expect(openTarget({ kind: 'url', url: 'javascript:alert(1)', preview_url: null })).toBeNull()
    expect(openTarget({ kind: 'url', url: 'data:text/html,<script>1</script>', preview_url: null })).toBeNull()
    expect(openTarget({ kind: 'url', url: 'not a url', preview_url: null })).toBeNull()
  })
})
