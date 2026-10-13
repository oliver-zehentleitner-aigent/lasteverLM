import { describe, expect, it } from 'vitest'
import { effectiveTheme, getTheme, isTheme, setTheme, subscribeTheme, toggledTheme } from './theme'

describe('theme', () => {
  it('toggles between light and dark only, from what is on screen', () => {
    expect(toggledTheme('light', true)).toBe('dark')
    expect(toggledTheme('dark', false)).toBe('light')
    // under "system" it sets the explicit opposite of the system's choice
    expect(toggledTheme('system', true)).toBe('light')
    expect(toggledTheme('system', false)).toBe('dark')
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
    // a dark system: under "system" the toggle offers light
    expect(toggledTheme(getTheme(), true)).toBe('light')
    // the settings page saves "light" through the store
    setTheme('light')
    expect(getTheme()).toBe('light')
    expect(toggledTheme(getTheme(), true)).toBe('dark')
    expect(seen).toBe(2)
    off()
    setTheme('dark')
    expect(seen).toBe(2)
    setTheme('system')
  })
})
