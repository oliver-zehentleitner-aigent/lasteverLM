// @vitest-environment jsdom
// DOMPurify needs a DOM: the labels are cleaned with the app's own sanitizer
import { describe, expect, it } from 'vitest'
import { Transformer } from 'markmap-lib'
import { cleanTree, toMarkdown } from './mindmap'
import { sanitizeHtml } from './sanitize'

describe('toMarkdown', () => {
  it('writes the root as heading and children as a nested list', () => {
    const md = toMarkdown({ label: 'Root', children: [{ label: 'A', children: [{ label: 'A1' }] }, { label: 'B' }] })
    expect(md).toBe('# Root\n- A\n  - A1\n- B')
  })
  it('handles a root without children', () => {
    expect(toMarkdown({ label: 'Only' })).toBe('# Only')
  })
})

describe('labels', () => {
  it('keeps a label with a line break on one node', () => {
    expect(toMarkdown({ label: 'Root', children: [{ label: 'A\n# not a heading' }] })).toBe('# Root\n- A # not a heading')
  })

  it('reach markmap as raw HTML, so the tree has to be cleaned', () => {
    const { root } = new Transformer().transform(toMarkdown({ label: 'R <img src=x onerror=alert(1)>', children: [{ label: '<b>A</b>' }] }))
    expect(root.content).toContain('onerror')
    const cleaned = cleanTree(root, sanitizeHtml)
    expect(cleaned.content).not.toContain('onerror')
    expect(cleaned.content).toContain('R ')
    // harmless markup stays, as markmap renders it
    expect(cleaned.children?.[0].content).toBe('<b>A</b>')
  })
})

describe('toMarkdown with markers', () => {
  it('appends what each node rests on to its label', () => {
    const md = toMarkdown({ label: 'Root', children: [{ label: 'Child', refs: [2] }] }, 0, (n) => (n.refs ? ` [${n.refs.join(',')}]` : ''))
    expect(md).toBe('# Root\n- Child [2]')
  })
})
