import { describe, expect, it } from 'vitest'
import { effectiveTheme, getTheme, isTheme, nextTheme, setTheme, subscribeTheme } from './theme'

describe('theme', () => {
  it('cycles system, light, dark', () => {
    expect(nextTheme('system')).toBe('light')
    expect(nextTheme('light')).toBe('dark')
    expect(nextTheme('dark')).toBe('system')
  })

  it('accepts only the three names and resolves system', () => {
    expect(isTheme('dark')).toBe(true)
    expect(isTheme('blue')).toBe(false)
    expect(effectiveTheme('system', true)).toBe('dark')
    expect(effectiveTheme('system', false)).toBe('light')
    expect(effectiveTheme('light', true)).toBe('light')
  })
})

describe('theme store', () => {
  it('a save in the settings changes what the header toggle offers next', () => {
    let seen = 0
    const off = subscribeTheme(() => (seen += 1))
    setTheme('system')
    // what the toggle shows before: "system", offering light next
    expect(nextTheme(getTheme())).toBe('light')
    // the settings page saves "light" through the store
    setTheme('light')
    expect(getTheme()).toBe('light')
    expect(nextTheme(getTheme())).toBe('dark')
    expect(seen).toBe(2)
    off()
    setTheme('dark')
    expect(seen).toBe(2)
    setTheme('system')
  })
})
