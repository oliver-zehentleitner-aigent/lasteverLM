/// <reference types="node" />
// the stylesheet as text; vitest does not process CSS imports
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { LEFT_WIDTH } from './layout'

const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')
const rem = (s: string) => Number(s.replace('rem', ''))

describe('the 3 x 2 output-format grid', () => {
  it('sets the middle column default and the divider minimum', () => {
    const tile = rem(/\.tiles \.tile-grid \{ grid-template-columns: repeat\(3, ([\d.]+rem)\); \}/.exec(css)![1])
    const gap = rem(/\.tile-grid \{[^}]*gap: ([\d.]+rem);/.exec(css)![1])
    const pad = rem(/\.tiles \{ padding: [\d.]+rem ([\d.]+rem);/.exec(css)![1])
    const root = Number(/font-size: (\d+)px;/.exec(css)![1])
    const width = 3 * tile + 2 * gap + 2 * pad
    expect(css).toContain(`var(--left-w, ${width}rem)`)
    expect(LEFT_WIDTH.min).toBe(width * root)
  })
})
