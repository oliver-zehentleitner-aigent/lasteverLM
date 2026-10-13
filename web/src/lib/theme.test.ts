import { describe, expect, it } from 'vitest'
import { isTheme, nextTheme } from './theme'

describe('theme', () => {
  it('cycles system, light, dark', () => {
    expect(nextTheme('system')).toBe('light')
    expect(nextTheme('light')).toBe('dark')
    expect(nextTheme('dark')).toBe('system')
  })

  it('accepts only the three names', () => {
    expect(isTheme('dark')).toBe(true)
    expect(isTheme('blue')).toBe(false)
    expect(isTheme(null)).toBe(false)
  })
})
