import { afterEach, describe, expect, it } from 'vitest'
import { failureMessage } from '../api/client'
import { describeRateLimit } from '../lib/ratelimit'
import { formFor } from '../lib/outputs'
import { setLanguage, t, tn } from '.'
import { de } from './de'
import { en } from './en'
import { interpolate, pickLanguage } from './translate'

describe('pickLanguage', () => {
  it('takes the preference, then the browser, then English', () => {
    expect(pickLanguage('de', ['en-US'])).toBe('de')
    expect(pickLanguage(null, ['fr-FR', 'de-AT', 'en'])).toBe('de')
    expect(pickLanguage(undefined, ['fr'])).toBe('en')
    expect(pickLanguage(null, [])).toBe('en')
  })
})

describe('interpolate', () => {
  it('fills placeholders and keeps unknown ones visible', () => {
    expect(interpolate('Delete "{name}"?', { name: 'notes.txt' })).toBe('Delete "notes.txt"?')
    expect(interpolate('{n} of {total}', { n: 2 })).toBe('2 of {total}')
    expect(interpolate('plain')).toBe('plain')
  })
})

describe('translations', () => {
  it('use the same placeholders in both languages', () => {
    const names = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()
    for (const key of Object.keys(en) as (keyof typeof en)[]) {
      expect([key, names(de[key])]).toEqual([key, names(en[key])])
    }
  })
})

describe('t() in German', () => {
  afterEach(() => setLanguage('en'))

  it('follows the current language, plurals included', () => {
    setLanguage('de')
    expect(t('tiles.create')).toBe('Erzeugen')
    expect(tn('rl.minutes', 1)).toBe('1 Minute')
    expect(tn('rl.minutes', 15)).toBe('15 Minuten')
    expect(formFor('report').label).toBe('Bericht')
    setLanguage('en')
    expect(formFor('report').label).toBe('Report')
  })

  it('renders the rate-limit rule and failure texts in German', () => {
    setLanguage('de')
    expect(describeRateLimit({ per_minute: 120, block_minutes: 15, ban_after_strikes: 3, strike_window_hours: 24, ban_max_days: 90, retention_days: 30 })).toBe(
      'Mehr als 120 Anfragen pro Minute von einer IP: 15 Minuten gesperrt, ein Verstoß. 3 Verstöße innerhalb von 24 Stunden: gebannt, bis ein Admin den Bann aufhebt, höchstens 90 Tage.',
    )
    expect(failureMessage(413, '')).toBe('Die Datei ist zu groß für den Server (HTTP 413)')
  })
})
