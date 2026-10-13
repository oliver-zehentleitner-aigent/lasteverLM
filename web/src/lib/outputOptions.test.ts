import { describe, expect, it } from 'vitest'
import type { OutputOptionsSpec } from '../api/types'
import { buildOptions, defaultValues, optionsLabel, sampleLanguage, speedSteps, voiceGroups } from './outputOptions'

const spec: OutputOptionsSpec = {
  languages: [
    { code: 'en', label: 'English' },
    { code: 'de', label: 'Deutsch' },
  ],
  audio: {
    voices: [
      { id: 'ryan', label: 'Ryan', gender: 'male', language: 'en' },
      { id: 'vivian', label: 'Vivian', gender: 'female', language: 'zh' },
    ],
    default_voice: 'ryan',
    speed: { min: 0.75, max: 1.5, step: 0.25, default: 1 },
  },
  kinds: { report: ['language'], audio: ['language', 'voice', 'speed'] },
}

describe('output options', () => {
  it('starts from the preferences, else the defaults; language follows the sources without one', () => {
    expect(defaultValues(spec, undefined)).toEqual({ language: '', voice: 'ryan', speed: 1 })
    expect(defaultValues(spec, { ui_language: null, output_language: 'de', audio_voice: 'vivian' })).toEqual({
      language: 'de',
      voice: 'vivian',
      speed: 1,
    })
    // a stored value the spec no longer offers falls back
    expect(defaultValues(spec, { ui_language: null, output_language: 'xx', audio_voice: 'alloy' }).voice).toBe('ryan')
  })

  it('sends only the keys the kind takes, language only when chosen', () => {
    const v = { language: 'de', voice: 'vivian', speed: 1.25 }
    expect(buildOptions('report', spec, v)).toEqual({ language: 'de' })
    expect(buildOptions('audio', spec, v)).toEqual({ language: 'de', voice: 'vivian', speed: 1.25 })
    expect(buildOptions('report', spec, { ...v, language: '' })).toEqual({})
    expect(buildOptions('quiz', spec, v)).toEqual({})
  })

  it('lists speeds on the step and groups voices', () => {
    expect(speedSteps(spec)).toEqual([0.75, 1, 1.25, 1.5])
    expect(voiceGroups(spec).map((g) => [g.gender, g.voices.map((x) => x.id)])).toEqual([
      ['female', ['vivian']],
      ['male', ['ryan']],
    ])
  })

  it('labels what a document was made with', () => {
    expect(optionsLabel({ language: 'de', voice: 'ryan', speed: 1.25 }, spec)).toBe('Deutsch · Ryan · 1.25×')
    expect(optionsLabel({}, spec)).toBeNull()
    expect(optionsLabel({ language: 'fr' }, null)).toBe('fr')
  })
})

describe('sampleLanguage', () => {
  it('takes the chosen language, else the interface language, else none', () => {
    expect(sampleLanguage('de', spec, 'en')).toBe('de')
    expect(sampleLanguage('', spec, 'de')).toBe('de')
    expect(sampleLanguage(null, spec, 'fr')).toBeUndefined()
    expect(sampleLanguage('xx', spec, 'en')).toBe('en')
  })
})
