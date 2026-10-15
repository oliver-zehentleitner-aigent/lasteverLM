import { describe, expect, it } from 'vitest'
import { t } from '../i18n'
import { TOUR_CREDIT, TOUR_STEPS, noteTourDone, signalCreditStep, tourDone, tourEvents } from './tour'

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

describe('the steps', () => {
  it('go through the notebook in seven steps, the credit step last', () => {
    expect(TOUR_STEPS.map((s) => s.key)).toEqual(['notebook', 'sources', 'format', 'outputs', 'viewer', 'chat', 'credit'])
    expect(TOUR_STEPS.filter((s) => 'credit' in s && s.credit).map((s) => s.key)).toEqual(['credit'])
    // the credit step outlines the menu's item and the dialog together
    expect(TOUR_STEPS[6].targets).toEqual(['.profile-menu [data-item="redeem"]', '.voucher-dialog'])
  })

  it('each has a title and a text', () => {
    for (const s of TOUR_STEPS) {
      expect(t(`tour.${s.key}.title` as never)).not.toBe(`tour.${s.key}.title`)
      expect(t(`tour.${s.key}` as never)).not.toBe(`tour.${s.key}`)
    }
    expect(t('tour.credit')).toBe('Credit comes from vouchers. Redeem one here, from the profile menu.')
  })

  it('signals the credit step on and off', () => {
    const seen: boolean[] = []
    const on = (e: Event) => seen.push((e as CustomEvent<boolean>).detail)
    tourEvents.addEventListener(TOUR_CREDIT, on)
    signalCreditStep(true)
    signalCreditStep(false)
    tourEvents.removeEventListener(TOUR_CREDIT, on)
    expect(seen).toEqual([true, false])
  })
})
