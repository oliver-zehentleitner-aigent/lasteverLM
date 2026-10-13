/** The pure part of the translation layer: language choice and {name}
 *  placeholders. Kept apart from React so it is tested on its own. */

export type Language = 'en' | 'de'

export const LANGUAGES: readonly Language[] = ['en', 'de']

/** The UI language: the user's preference when set, else the browser's
 *  first language we have, else English. */
export function pickLanguage(preference: Language | null | undefined, browser: readonly string[]): Language {
  if (preference && LANGUAGES.includes(preference)) return preference
  for (const tag of browser) {
    const base = tag.toLowerCase().split('-')[0] as Language
    if (LANGUAGES.includes(base)) return base
  }
  return 'en'
}

/** Replaces {name} with vars.name; an unknown placeholder stays visible,
 *  so a missing value shows up in the UI instead of an empty gap. */
export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole))
}
