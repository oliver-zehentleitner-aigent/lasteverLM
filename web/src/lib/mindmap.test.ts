import { describe, expect, it } from 'vitest'
import { toMarkdown } from './mindmap'

describe('toMarkdown', () => {
  it('writes the root as heading and children as a nested list', () => {
    const md = toMarkdown({ label: 'Root', children: [{ label: 'A', children: [{ label: 'A1' }] }, { label: 'B' }] })
    expect(md).toBe('# Root\n- A\n  - A1\n- B')
  })
  it('handles a root without children', () => {
    expect(toMarkdown({ label: 'Only' })).toBe('# Only')
  })
})
