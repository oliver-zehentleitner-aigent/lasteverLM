import { describe, expect, it } from 'vitest'
import type { OutputOptionsSpec } from '../api/types'
import { buildOptions, defaultValues, optionsLabel, sampleLanguage, secondVoice, speakerName, speedSteps, voiceGroups, twoVoices } from './outputOptions'

const spec: OutputOptionsSpec = {
  languages: [
    { code: 'en', label: 'English' },
    { code: 'de', label: 'Deutsch' },
  ],
  audio: {
    voices: [
      { id: 'ryan', label: 'Ryan', gender: 'male', language: 'en' },
      { id: 'vivian', label: 'Vivian', gender: 'female', language: 'zh' },
      { id: 'aiden', label: 'Aiden', gender: 'male', language: 'en' },
      { id: 'serena', label: 'Serena', gender: 'female', language: 'zh' },
      { id: 'sohee', label: 'Sohee', gender: 'female', language: 'ko' },
    ],
    default_voice: 'ryan',
    speed: { min: 0.75, max: 1.5, step: 0.25, default: 1 },
  },
  kinds: { report: ['language'], audio: ['language', 'voice', 'speed', 'audio_style', 'audio_voice_2'] },
}

describe('output options', () => {
  it('starts from the preferences, else the defaults; language follows the sources without one', () => {
    expect(defaultValues(spec, undefined)).toMatchObject({ language: '', voice: 'ryan', speed: 1, style: 'overview', voice2: 'aiden' })
    expect(defaultValues(spec, { ui_language: null, output_language: 'de', audio_voice: 'vivian' })).toMatchObject({
      language: 'de',
      voice: 'vivian',
      speed: 1,
      style: 'overview',
      voice2: 'serena',
    })
    // a stored value the spec no longer offers falls back
    expect(defaultValues(spec, { ui_language: null, output_language: 'xx', audio_voice: 'alloy' }).voice).toBe('ryan')
  })

  it('sends only the keys the kind takes, language only when chosen', () => {
    const v = { ...defaultValues(spec, undefined), language: 'de', voice: 'vivian', speed: 1.25, style: 'overview' as const, voice2: 'serena' }
    expect(buildOptions('report', spec, v)).toEqual({ language: 'de' })
    expect(buildOptions('audio', spec, v)).toEqual({ language: 'de', voice: 'vivian', speed: 1.25, audio_style: 'overview' })
    // the second voice only for a conversation (rag refuses it otherwise)
    expect(buildOptions('audio', spec, { ...v, style: 'conversation' })).toEqual({ language: 'de', voice: 'vivian', speed: 1.25, audio_style: 'conversation', audio_voice_2: 'serena' })
    expect(buildOptions('report', spec, { ...v, language: '' })).toEqual({})
    expect(buildOptions('quiz', spec, v)).toEqual({})
  })

  it('lists speeds on the step and groups voices', () => {
    expect(speedSteps(spec)).toEqual([0.75, 1, 1.25, 1.5])
    expect(voiceGroups(spec).map((g) => [g.gender, g.voices.map((x) => x.id)])).toEqual([
      ['female', ['vivian', 'serena', 'sohee']],
      ['male', ['ryan', 'aiden']],
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

describe('audio styles', () => {
  it('starts a conversation with another voice of the same language, else any other', () => {
    expect(secondVoice(spec, 'ryan')).toBe('aiden')
    expect(secondVoice(spec, 'aiden')).toBe('ryan')
    expect(secondVoice(spec, 'serena')).toBe('vivian')
    expect(secondVoice(spec, 'sohee')).toBe('ryan')
  })

  it('names a speaker by its voice, else by its role', () => {
    const o = { voice: 'ryan', audio_voice_2: 'vivian', audio_style: 'conversation' as const }
    expect(speakerName('interviewer', o, spec)).toBe('Ryan')
    expect(speakerName('expert', o, spec)).toBe('Vivian')
    expect(speakerName('expert', o, null)).toBe('Expert')
    expect(speakerName('narrator', {}, spec)).toBe('Narrator')
  })

  it('shows a conversation with both voices in the line under the title', () => {
    expect(optionsLabel({ voice: 'ryan', audio_voice_2: 'vivian', audio_style: 'conversation', speed: 1 }, spec)).toBe('Conversation · Ryan & Vivian · 1×')
    expect(optionsLabel({ voice: 'ryan', audio_style: 'overview', speed: 1 }, spec)).toBe('Ryan · 1×')
  })
})

describe('report and quiz options, and the instructions', () => {
  const full = {
    ...spec,
    report: { styles: ['briefing', 'academic'], default_style: 'briefing', lengths: ['short', 'medium', 'long'], default_length: 'medium' },
    quiz: { question_count: { min: 5, max: 30, default: 10 }, difficulties: ['easy', 'medium', 'hard'], default_difficulty: 'medium', audiences: ['adults', 'experts'], default_audience: 'adults' },
    kinds: {
      report: ['language', 'instructions', 'report_style', 'length'],
      quiz: ['language', 'instructions', 'question_count', 'difficulty', 'audience'],
      table: ['language', 'instructions'],
    },
  } as OutputOptionsSpec

  it("starts from rag's defaults", () => {
    expect(defaultValues(full, undefined)).toMatchObject({ instructions: '', reportStyle: 'briefing', length: 'medium', questionCount: 10, difficulty: 'medium', audience: 'adults' })
  })

  it('sends the keys each kind takes, the instructions only when not blank', () => {
    const v = { ...defaultValues(full, undefined), reportStyle: 'academic' as const, questionCount: 15, instructions: '  focus   on costs ' }
    expect(buildOptions('report', full, v)).toEqual({ instructions: 'focus on costs', report_style: 'academic', length: 'medium' })
    expect(buildOptions('quiz', full, v)).toEqual({ instructions: 'focus on costs', question_count: 15, difficulty: 'medium', audience: 'adults' })
    expect(buildOptions('table', full, { ...v, instructions: '   ' })).toEqual({})
  })

  it('names them in the line under the title', () => {
    expect(optionsLabel({ report_style: 'executive_summary', length: 'short' }, null)).toBe('Executive summary · short')
    expect(optionsLabel({ question_count: 10, difficulty: 'hard', audience: 'experts' }, null)).toBe('10 questions · hard · experts')
  })
})

describe('the judge option', () => {
  const judged = { ...spec, judge: { levels: ['off', 'low', 'medium', 'high'], default: 'off', models: { low: 'small' } }, kinds: { report: ['language', 'instructions', 'judge'] } } as OutputOptionsSpec
  it('sends a level only when it is not off', () => {
    const v = defaultValues(judged, undefined)
    expect(v.judge).toBe('off')
    expect(buildOptions('report', judged, v)).toEqual({})
    expect(buildOptions('report', judged, { ...v, judge: 'medium' })).toEqual({ judge: 'medium' })
  })

  it('starts from the user\'s default when rag offers that level', () => {
    const prefs = { ui_language: null, output_language: null, audio_voice: null, judge_default: 'high' as const }
    expect(defaultValues(judged, prefs).judge).toBe('high')
    const fewer = { ...judged, judge: { ...judged.judge!, levels: ['off', 'low'] } } as OutputOptionsSpec
    expect(defaultValues(fewer, prefs).judge).toBe('off')
  })
})

describe('twoVoices', () => {
  it('is a conversation and an FAQ', () => {
    expect(twoVoices('conversation')).toBe(true)
    expect(twoVoices('faq')).toBe(true)
    expect(twoVoices('overview')).toBe(false)
    expect(twoVoices(undefined)).toBe(false)
  })
})
