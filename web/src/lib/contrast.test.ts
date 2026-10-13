/// <reference types="node" />
// the stylesheet as text; vitest does not process CSS imports, ?raw included
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('../styles.css', import.meta.url), 'utf8')

/** The token values of one block of styles.css, by its selector line. */
function tokens(selector: string): Record<string, string> {
  const start = css.indexOf(selector)
  const body = css.slice(start, css.indexOf('}', start))
  return Object.fromEntries([...body.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]))
}

function luminance(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}

function ratio(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

const light = tokens(':root {')
const dark = { ...light, ...tokens(":root[data-theme='dark'] {") }

/** Text pairs need 4.5:1 (WCAG AA), large or non-text parts 3:1. */
const TEXT: [string, string][] = [
  ['--fg', '--bg'],
  ['--fg', '--panel'],
  ['--muted', '--bg'],
  ['--muted', '--panel'],
  ['--accent', '--panel'],
  ['--accent', '--bg'],
  ['--on-accent', '--accent'],
  ['--fg', '--accent-soft'],
  ['--danger', '--panel'],
  ['--ok', '--panel'],
  // badge text, an open citation marker, the provenance mark
  ['--warn', '--panel'],
  ['--accent', '--accent-soft'],
  ['--muted', '--accent-soft'],
]
const UI: [string, string][] = [
  ['--chart-1', '--panel'],
  ['--chart-2', '--panel'],
  ['--chart-3', '--panel'],
  ['--chart-4', '--panel'],
  ['--chart-5', '--panel'],
  ['--chart-6', '--panel'],
]

describe.each([
  ['light', light],
  ['dark', dark],
])('%s theme contrast', (_name, t) => {
  it.each(TEXT)('%s on %s is at least 4.5:1', (fg, bg) => {
    expect(ratio(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5)
  })
  it.each(UI)('%s on %s is at least 3:1', (fg, bg) => {
    expect(ratio(t[fg], t[bg])).toBeGreaterThanOrEqual(3)
  })
})

describe('the two dark blocks', () => {
  it('hold the same values', () => {
      const media = css.slice(css.indexOf(":root:not([data-theme='light'])"))
    const fromMedia = Object.fromEntries([...media.slice(0, media.indexOf('}')).matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2]]))
    const forced = css.slice(css.indexOf(":root[data-theme='dark'] {"))
    const fromForced = Object.fromEntries([...forced.slice(0, forced.indexOf('}')).matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2]]))
    expect(fromMedia).toEqual(fromForced)
  })
})
