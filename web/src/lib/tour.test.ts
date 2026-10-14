import { describe, expect, it } from 'vitest'
import { noteTourDone, tourDone } from './tour'

const memory = () => {
  const m = new Map<string, string>()
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) }
}

describe('tourDone', () => {
  it('follows the preference, else this browser\'s note', () => {
    const s = memory()
    expect(tourDone({ id: 'u1', preferences: { ui_language: null, output_language: null, audio_voice: null, tour_done: true } }, s)).toBe(true)
    expect(tourDone({ id: 'u1', preferences: { ui_language: null, output_language: null, audio_voice: null, tour_done: false } }, s)).toBe(false)
    noteTourDone(s, 'u1', true)
    expect(tourDone({ id: 'u1' }, s)).toBe(true)
    expect(tourDone({ id: 'u2' }, s)).toBe(false)
    noteTourDone(s, 'u1', false)
    expect(tourDone({ id: 'u1' }, s)).toBe(false)
  })

  it('shows nothing before the account is known', () => {
    expect(tourDone(null, memory())).toBe(true)
  })
})
