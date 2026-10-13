import { de } from './de'
import { en, type MessageKey } from './en'
import { interpolate, type Language } from './translate'

export type { MessageKey } from './en'
export type { Language } from './translate'

const MAPS: Record<Language, Record<MessageKey, string>> = { en, de }

let current: Language = 'en'

/** The app's language for everything t() returns, set by App from the
 *  user's preference (the browser's language before login). One language
 *  at a time, so a module-level value is enough; App re-renders the tree
 *  when it changes. */
export function setLanguage(lang: Language): void {
  current = lang
}

export function language(): Language {
  return current
}

/** The text for a key in the current language, {name} filled from vars. */
export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  return interpolate(MAPS[current][key] ?? en[key], vars)
}

/** A count with its noun: `${key}.one` for 1, `${key}.other` otherwise,
 *  {n} filled in. Enough for English and German. */
export function tn(key: string, n: number, vars?: Record<string, string | number>): string {
  return t(`${key}.${n === 1 ? 'one' : 'other'}` as MessageKey, { n: n.toLocaleString(current), ...vars })
}
