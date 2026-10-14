import { describe, expect, it } from 'vitest'
import { citationTarget, openTarget } from './openEntry'

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

describe('citationTarget', () => {
  const signed = 'https://ams1.vultrobjects.com/bucket/key.pdf?X-Amz-Signature=abc'

  it('opens a PDF on the cited page', () => {
    expect(citationTarget({ kind: 'pdf', preview_url: signed }, 4)).toBe(signed + '#page=4')
  })

  it('leaves the page off when the citation has none, or a nonsense one', () => {
    expect(citationTarget({ kind: 'pdf', preview_url: signed }, null)).toBe(signed)
    expect(citationTarget({ kind: 'pdf', preview_url: signed }, 0)).toBe(signed)
    expect(citationTarget({ kind: 'pdf', preview_url: signed }, 2.5)).toBe(signed)
  })

  it('anchors only a PDF', () => {
    expect(citationTarget({ kind: 'text', preview_url: signed }, 3)).toBe(signed)
    expect(citationTarget({ kind: 'url', preview_url: 'https://en.wikipedia.org/wiki/Danube' }, 3)).toBe('https://en.wikipedia.org/wiki/Danube')
  })

  it('has nothing to open without a preview or a source', () => {
    expect(citationTarget({ kind: 'pdf', preview_url: null }, 2)).toBeNull()
    expect(citationTarget({ kind: 'pdf' }, 2)).toBeNull()
    expect(citationTarget(undefined, 2)).toBeNull()
  })

  it('never opens a script address', () => {
    expect(citationTarget({ kind: 'url', preview_url: 'javascript:alert(1)' }, null)).toBeNull()
  })
})
