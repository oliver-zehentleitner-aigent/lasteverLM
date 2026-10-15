/// <reference types="node" />
// the stylesheet as text; vitest does not process CSS imports
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { LEFT_WIDTH, STACKED_QUERY } from './layout'

const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')
const rem = (s: string) => Number(s.replace('rem', ''))

describe('the output-format grid', () => {
  it('flows with the column, three tiles a row still fitting its narrowest width', () => {
    const tile = Number(/\.tiles \.tile-grid \{ grid-template-columns: repeat\(auto-fill, minmax\((\d+)px, 1fr\)\);/.exec(css)![1])
    const gap = rem(/\.tile-grid \{[^}]*gap: ([\d.]+rem);/.exec(css)![1])
    const pad = rem(/\.tiles \{ padding: [\d.]+rem ([\d.]+rem);/.exec(css)![1])
    const root = Number(/font-size: (\d+)px;/.exec(css)![1])
    // the column widths stay: the default and the divider's minimum are 27rem
    expect(css).toContain('var(--left-w, 27rem)')
    expect(LEFT_WIDTH.min).toBe(27 * root)
    expect(3 * tile + (2 * gap + 2 * pad) * root).toBeLessThanOrEqual(LEFT_WIDTH.min)
    // every tile as tall as the tallest, in every row
    expect(css).toMatch(/\.tiles \.tile-grid \{[^}]*grid-auto-rows: 1fr;/)
  })
})

describe('the stacked layout', () => {
  it('starts where the script thinks the chat is below the fold', () => {
    expect(css).toContain(`@media ${STACKED_QUERY} {\n  .workspace {`)
  })
})
