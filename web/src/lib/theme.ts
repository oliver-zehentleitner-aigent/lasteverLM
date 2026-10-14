import { useEffect, useState, useSyncExternalStore } from 'react'

/** "system" follows the operating system's light or dark setting. */
export type Theme = 'system' | 'light' | 'dark'

const KEY = 'lasteverlm.theme'
const SESSION_KEY = 'lasteverlm.theme.session'

export function isTheme(v: unknown): v is Theme {
  return v === 'system' || v === 'light' || v === 'dark'
}

/** With nothing chosen anywhere the app is light. */
export const DEFAULT_THEME: Theme = 'light'

/** The saved choice as this browser last knew it (the account preference
 *  mirrored, or what was chosen before signing in); index.html reads the
 *  same keys before the first paint, so the page never flashes the wrong
 *  colours. */
export function readStoredTheme(): Theme {
  return readKey(() => window.localStorage, KEY) ?? DEFAULT_THEME
}

/** The header toggle's choice for this browser session only; null when none. */
export function readSessionTheme(): Theme | null {
  return readKey(() => window.sessionStorage, SESSION_KEY)
}

function readKey(storage: () => Storage, key: string): Theme | null {
  try {
    const v = typeof window === 'undefined' ? null : storage().getItem(key)
    return isTheme(v) ? v : null
  } catch {
    return null
  }
}

// The one theme store. The saved choice (Settings, the account) and the
// session's override (the header toggle) are kept apart; what is on screen
// is the override when there is one, else the saved choice.
let saved: Theme = readStoredTheme()
let session: Theme | null = readSessionTheme()
const listeners = new Set<() => void>()

/** What is on screen now: the session's override, else the saved choice. */
export function getTheme(): Theme {
  return session ?? saved
}

export function getSavedTheme(): Theme {
  return saved
}

export function getSessionTheme(): Theme | null {
  return session
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function apply(): void {
  const theme = getTheme()
  if (typeof document !== 'undefined') {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
  }
  for (const l of listeners) l()
}

/** Sets the saved choice (Settings, or the account's preference arriving)
 *  and this browser's memory of it. A session override stays on top. */
export function setTheme(theme: Theme): void {
  saved = theme
  try {
    window.localStorage.setItem(KEY, theme)
  } catch {
    // not remembered; the account preference still carries it
  }
  apply()
}

/** The header toggle: this browser session only, nothing is saved in the
 *  account; null drops the override and the saved choice shows again. */
export function setSessionTheme(theme: Theme | null): void {
  session = theme
  try {
    if (theme) window.sessionStorage.setItem(SESSION_KEY, theme)
    else window.sessionStorage.removeItem(SESSION_KEY)
  } catch {
    // kept for this page only
  }
  apply()
}

/** The choice resolved to the colours on screen. */
export function effectiveTheme(theme: Theme, systemDark: boolean): 'light' | 'dark' {
  return theme === 'system' ? (systemDark ? 'dark' : 'light') : theme
}

/** What the header toggle sets: always the opposite of what is on screen,
 *  so from "system" it turns into an explicit light or dark. "system" itself
 *  is only chosen on the settings page. */
export function toggledTheme(theme: Theme, systemDark: boolean): 'light' | 'dark' {
  return effectiveTheme(theme, systemDark) === 'dark' ? 'light' : 'dark'
}

/** Whether the operating system asks for dark right now. */
export function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && (window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false)
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
