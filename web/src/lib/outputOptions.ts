import type { Audience, AudioStyle, Difficulty, OutputKind, OutputOption, OutputOptions, OutputOptionsSpec, Preferences, ReportLength, ReportStyle } from '../api/types'
import { t } from '../i18n'

/** The option values a form holds; '' for language means "same as the sources". */
export interface OptionValues {
  language: string
  voice: string
  speed: number
  style: AudioStyle
  /** the second speaker, sent only for a conversation */
  voice2: string
  /** the author's instructions; sent only when not blank */
  instructions: string
  reportStyle: ReportStyle
  length: ReportLength
  questionCount: number
  difficulty: Difficulty
  audience: Audience
}

/** rag's limit for the instructions, when the catalogue does not say. */
export const INSTRUCTIONS_MAX = 500

export const AUDIO_STYLES: AudioStyle[] = ['overview', 'story', 'conversation']

/** The second speaker a conversation starts with, as rag picks it when
 *  none is sent: the next voice in the catalogue with the first one's
 *  native language, else any other voice (rag refuses the same twice). */
export function secondVoice(spec: OutputOptionsSpec, first: string): string {
  const voices = spec.audio.voices
  const lang = voices.find((v) => v.id === first)?.language
  return (voices.find((v) => v.id !== first && v.language === lang) ?? voices.find((v) => v.id !== first))?.id ?? first
}

/** Who speaks a transcript turn, by role: the voice's name from the
 *  catalogue (the narrator and the interviewer speak with `voice`, the
 *  expert with `audio_voice_2`), else the role's own name. */
export function speakerName(speaker: string, o: OutputOptions | undefined, spec: OutputOptionsSpec | null): string {
  const id = speaker === 'expert' ? o?.audio_voice_2 : o?.voice
  const label = id ? spec?.audio.voices.find((v) => v.id === id)?.label : undefined
  if (label) return label
  return speaker === 'interviewer' || speaker === 'expert' || speaker === 'narrator' ? t(`speaker.${speaker}`) : speaker
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
  const voice = prefs?.audio_voice && voiceIds.has(prefs.audio_voice) ? prefs.audio_voice : spec.audio.default_voice
  return {
    language: prefs?.output_language && langCodes.has(prefs.output_language) ? prefs.output_language : '',
    voice,
    speed: spec.audio.speed.default,
    style: 'overview',
    voice2: secondVoice(spec, voice),
    instructions: '',
    reportStyle: spec.report?.default_style ?? 'briefing',
    length: spec.report?.default_length ?? 'medium',
    questionCount: spec.quiz?.question_count.default ?? 10,
    difficulty: spec.quiz?.default_difficulty ?? 'medium',
    audience: spec.quiz?.default_audience ?? 'adults',
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
    if (key === 'audio_style') out.audio_style = v.style
    if (key === 'audio_voice_2' && v.style === 'conversation') out.audio_voice_2 = v.voice2
    if (key === 'instructions' && v.instructions.trim()) out.instructions = v.instructions.trim().replace(/\s+/g, ' ')
    if (key === 'report_style') out.report_style = v.reportStyle
    if (key === 'length') out.length = v.length
    if (key === 'question_count') out.question_count = v.questionCount
    if (key === 'difficulty') out.difficulty = v.difficulty
    if (key === 'audience') out.audience = v.audience
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

/** "Deutsch · Ryan · 1.25×" for a made document, "Deutsch · Conversation ·
 *  Ryan & Vivian · 1×" for a conversation; null when it has none. */
export function optionsLabel(o: OutputOptions | undefined, spec: OutputOptionsSpec | null): string | null {
  if (!o) return null
  const parts: string[] = []
  if (o.language) parts.push(spec?.languages.find((l) => l.code === o.language)?.label ?? o.language)
  if (o.audio_style && o.audio_style !== 'overview') parts.push(t(`audioStyle.${o.audio_style}`))
  const voiceLabel = (id: string) => spec?.audio.voices.find((v) => v.id === id)?.label ?? id
  if (o.voice) parts.push(o.audio_style === 'conversation' && o.audio_voice_2 ? `${voiceLabel(o.voice)} & ${voiceLabel(o.audio_voice_2)}` : voiceLabel(o.voice))
  if (o.speed !== undefined) parts.push(`${o.speed}×`)
  if (o.report_style) parts.push(t(`opt.reportStyle.${o.report_style}`))
  if (o.length) parts.push(t(`opt.length.${o.length}`))
  if (o.question_count !== undefined) parts.push(t('opt.questions', { n: o.question_count }))
  if (o.difficulty) parts.push(t(`opt.difficulty.${o.difficulty}`))
  if (o.audience) parts.push(t(`opt.audience.${o.audience}`))
  return parts.length ? parts.join(' · ') : null
}

/** The language a voice sample is spoken in: the chosen document language,
 *  else the interface language when rag offers it, else rag's default. */
export function sampleLanguage(chosen: string | null | undefined, spec: OutputOptionsSpec, uiLanguage: string): string | undefined {
  const offered = (code: string) => spec.languages.some((l) => l.code === code)
  if (chosen && offered(chosen)) return chosen
  return offered(uiLanguage) ? uiLanguage : undefined
}
