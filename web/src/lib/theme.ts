import { useEffect, useState, useSyncExternalStore } from 'react'

/** "system" follows the operating system's light or dark setting. */
export type Theme = 'system' | 'light' | 'dark'

const KEY = 'lasteverlm.theme'

export function isTheme(v: unknown): v is Theme {
  return v === 'system' || v === 'light' || v === 'dark'
}

/** The theme this browser last used; index.html reads the same key before
 *  the first paint, so the page never flashes the wrong colours. */
export function readStoredTheme(): Theme {
  try {
    const v = typeof window === 'undefined' ? null : window.localStorage.getItem(KEY)
    return isTheme(v) ? v : 'system'
  } catch {
    return 'system'
  }
}

// The one theme store. The header toggle, the settings page and App all
// read and write it, so they can never disagree about the current choice.
let current: Theme = readStoredTheme()
const listeners = new Set<() => void>()

export function getTheme(): Theme {
  return current
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Sets the theme: the store, the page (`data-theme` on <html>, none for
 *  "system") and this browser's memory, then tells every subscriber. */
export function setTheme(theme: Theme): void {
  current = theme
  if (typeof document !== 'undefined') {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
  }
  try {
    window.localStorage.setItem(KEY, theme)
  } catch {
    // not remembered; the account preference still carries it
  }
  for (const l of listeners) l()
}

/** The choice resolved to the colours on screen. */
export function effectiveTheme(theme: Theme, systemDark: boolean): 'light' | 'dark' {
  return theme === 'system' ? (systemDark ? 'dark' : 'light') : theme
}

/** The header toggle's order. */
export function nextTheme(t: Theme): Theme {
  return t === 'system' ? 'light' : t === 'light' ? 'dark' : 'system'
}

/** The current choice, re-rendering on every change. */
export function useTheme(): Theme {
  return useSyncExternalStore(subscribeTheme, getTheme, getTheme)
}

/** Bumps whenever the colours on screen change (a choice, or the system
 *  switching under "system"), for code that reads colours as values. */
export function useThemeVersion(): number {
  const [v, setV] = useState(0)
  useEffect(() => {
    const bump = () => setV((x) => x + 1)
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const off = subscribeTheme(bump)
    media?.addEventListener?.('change', bump)
    return () => {
      off()
      media?.removeEventListener?.('change', bump)
    }
  }, [])
  return v
}
