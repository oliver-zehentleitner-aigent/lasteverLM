import { useEffect, useState } from 'react'
import { account } from '../api/account'
import { useMe } from '../hooks/useMe'
import { t } from '../i18n'
import { browserStorage } from '../lib/layout'
import { noteTourDone, TOUR_STEPS, tourDone } from '../lib/tour'

type Rect = { top: number; left: number; width: number; height: number }

const PAD = 6

/** The first-login introduction: three steps, each with its area
 *  outlined over a dimmed page and a card with an arrow beside it. Next,
 *  Back, Skip; done in three clicks. Shown once per user: finishing or
 *  skipping sets the account's `tour_done` (and a note in this browser,
 *  for the shared demo user, which cannot keep preferences). Settings can
 *  show it again. */
export function Tour() {
  const { me, setMe } = useMe()
  const [hidden, setHidden] = useState(false)
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const show = !hidden && !tourDone(me, browserStorage())
  const s = TOUR_STEPS[step]
  const noCredit = me !== null && me !== undefined && me.balance_cents <= 0

  // the area's place, after it is scrolled into view; again on resize and scroll
  useEffect(() => {
    if (!show) return
    const el = document.querySelector<HTMLElement>(s.target)
    el?.scrollIntoView({ block: 'nearest' })
    const measure = () => {
      const r = el?.getBoundingClientRect()
      setRect(r ? { top: r.top - PAD, left: r.left - PAD, width: r.width + 2 * PAD, height: r.height + 2 * PAD } : null)
    }
    const frame = requestAnimationFrame(measure)
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [show, s.target])

  if (!show || !me) return null

  function finish() {
    setHidden(true)
    noteTourDone(browserStorage(), me!.id, true)
    account.savePreferences({ tour_done: true }).then(setMe, () => {
      // the demo user (403) or an account service without the preference: this browser's note holds
    })
  }

  const last = step === TOUR_STEPS.length - 1
  const text = s.key === 'create' && noCredit ? t('tour.createNoCredit') : t(`tour.${s.key}`)
  // the card below the area when there is room, else above it
  const below = rect ? rect.top + rect.height + 180 < window.innerHeight : true
  const cardStyle = rect
    ? below
      ? { top: rect.top + rect.height + 12, left: Math.max(16, Math.min(rect.left, window.innerWidth - 336)) }
      : { top: Math.max(16, rect.top - 12), left: Math.max(16, Math.min(rect.left, window.innerWidth - 336)), transform: 'translateY(-100%)' }
    : { top: '30%', left: '50%', transform: 'translateX(-50%)' }

  return (
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {rect ? <div className="tour-spot" style={rect} /> : <div className="tour-dim" />}
      <div className={`tour-card ${below ? 'arrow-up' : 'arrow-down'}`} style={cardStyle}>
        <p className="muted small">{t('tour.step', { n: step + 1, total: TOUR_STEPS.length })}</p>
        <h2 id="tour-title">{t(`tour.${s.key}.title`)}</h2>
        <p>{text}</p>
        <div className="row tour-actions">
          <button type="button" className="link" onClick={finish}>
            {t('tour.skip')}
          </button>
          <span className="grow" />
          {step > 0 && (
            <button type="button" className="secondary small" onClick={() => setStep(step - 1)}>
              {t('tour.back')}
            </button>
          )}
          <button type="button" className="small" autoFocus onClick={() => (last ? finish() : setStep(step + 1))}>
            {last ? t('tour.done') : t('tour.next')}
          </button>
        </div>
      </div>
    </div>
  )
}
