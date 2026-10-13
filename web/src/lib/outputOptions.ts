import type { OutputKind, OutputOption, OutputOptions, OutputOptionsSpec, Preferences } from '../api/types'

/** The option values a form holds; '' for language means "same as the sources". */
export interface OptionValues {
  language: string
  voice: string
  speed: number
}

/** Which options a kind takes, in the order the form shows them. */
export function optionsFor(kind: OutputKind, spec: OutputOptionsSpec): OutputOption[] {
  return spec.kinds[kind] ?? []
}

/** Starting values: the user's preferences where set, the spec's defaults
 *  otherwise; language stays empty (same as sources) without a preference. */
export function defaultValues(spec: OutputOptionsSpec, prefs: Preferences | undefined): OptionValues {
  const voiceIds = new Set(spec.audio.voices.map((v) => v.id))
  const langCodes = new Set(spec.languages.map((l) => l.code))
  return {
    language: prefs?.output_language && langCodes.has(prefs.output_language) ? prefs.output_language : '',
    voice: prefs?.audio_voice && voiceIds.has(prefs.audio_voice) ? prefs.audio_voice : spec.audio.default_voice,
    speed: spec.audio.speed.default,
  }
}

/** The body's `options`: only the keys the kind takes, language left out
 *  when it should follow the sources, so rag's 422 for foreign keys never fires. */
export function buildOptions(kind: OutputKind, spec: OutputOptionsSpec, v: OptionValues): OutputOptions {
  const out: OutputOptions = {}
  for (const key of optionsFor(kind, spec)) {
    if (key === 'language' && v.language) out.language = v.language
    if (key === 'voice') out.voice = v.voice
    if (key === 'speed') out.speed = v.speed
  }
  return out
}

/** The speeds the select offers, from min to max on the step. */
export function speedSteps(spec: OutputOptionsSpec): number[] {
  const { min, max, step } = spec.audio.speed
  const n = Math.round((max - min) / step)
  return Array.from({ length: n + 1 }, (_, i) => Math.round((min + i * step) * 100) / 100)
}

/** Voices grouped for the select, female first then male. */
export function voiceGroups(spec: OutputOptionsSpec) {
  return (['female', 'male'] as const).map((gender) => ({ gender, voices: spec.audio.voices.filter((v) => v.gender === gender) }))
}

/** "Deutsch · Ryan · 1.25×" for a made document; null when it has none. */
export function optionsLabel(o: OutputOptions | undefined, spec: OutputOptionsSpec | null): string | null {
  if (!o) return null
  const parts: string[] = []
  if (o.language) parts.push(spec?.languages.find((l) => l.code === o.language)?.label ?? o.language)
  if (o.voice) parts.push(spec?.audio.voices.find((v) => v.id === o.voice)?.label ?? o.voice)
  if (o.speed !== undefined) parts.push(`${o.speed}×`)
  return parts.length ? parts.join(' · ') : null
}

/** The language a voice sample is spoken in: the chosen document language,
 *  else the interface language when rag offers it, else rag's default. */
export function sampleLanguage(chosen: string | null | undefined, spec: OutputOptionsSpec, uiLanguage: string): string | undefined {
  const offered = (code: string) => spec.languages.some((l) => l.code === code)
  if (chosen && offered(chosen)) return chosen
  return offered(uiLanguage) ? uiLanguage : undefined
}
