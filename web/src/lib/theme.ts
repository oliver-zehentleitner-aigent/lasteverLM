import { useEffect, useState } from 'react'

/** "system" follows the operating system's light or dark setting. */
export type Theme = 'system' | 'light' | 'dark'

const KEY = 'lasteverlm.theme'
const EVENT = 'lasteverlm-theme'

export function isTheme(v: unknown): v is Theme {
  return v === 'system' || v === 'light' || v === 'dark'
}

/** The theme this browser last used; index.html reads the same key before
 *  the first paint, so the page never flashes the wrong colours. */
export function readStoredTheme(): Theme {
  try {
    const v = window.localStorage.getItem(KEY)
    return isTheme(v) ? v : 'system'
  } catch {
    return 'system'
  }
}

/** Applies a theme to the page and remembers it in this browser. */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
  try {
    window.localStorage.setItem(KEY, theme)
  } catch {
    // not remembered; the account preference still carries it
  }
  window.dispatchEvent(new Event(EVENT))
}

/** The header toggle's order. */
export function nextTheme(t: Theme): Theme {
  return t === 'system' ? 'light' : t === 'light' ? 'dark' : 'system'
}

/** Bumps whenever the effective colours change (a chosen theme or the
 *  system switching), for code that reads colours as values (the charts). */
export function useThemeVersion(): number {
  const [v, setV] = useState(0)
  useEffect(() => {
    const bump = () => setV((x) => x + 1)
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    window.addEventListener(EVENT, bump)
    media?.addEventListener?.('change', bump)
    return () => {
      window.removeEventListener(EVENT, bump)
      media?.removeEventListener?.('change', bump)
    }
  }, [])
  return v
}
