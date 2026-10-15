import { useEffect, useState } from 'react'
import { account } from '../api/account'
import { useMe } from '../hooks/useMe'
import { t } from '../i18n'
import { browserStorage } from '../lib/layout'
import { noteTourDone, signalCreditStep, TOUR_STEPS, tourDone } from '../lib/tour'

type Rect = { top: number; left: number; width: number; height: number }

const PAD = 6

/** The areas a step outlines that are on screen: found, and with a size
 *  (a phone's stacked layout hides some). */
function measure(targets: readonly string[]): Rect[] {
  return targets.flatMap((sel) => {
    const r = document.querySelector<HTMLElement>(sel)?.getBoundingClientRect()
    return r && r.width > 0 && r.height > 0 ? [{ top: r.top - PAD, left: r.left - PAD, width: r.width + 2 * PAD, height: r.height + 2 * PAD }] : []
  })
}

/** The first-login introduction: seven steps through the notebook view,
 *  each with its areas outlined over a dimmed page and a card with an
 *  arrow beside the first. Next, Back, Skip. The last step opens the
 *  profile menu and the voucher dialog and outlines both; leaving it
 *  closes them, nothing is redeemed. Shown once per user: finishing or
 *  skipping sets the account's `tour_done` (and a note in this browser,
 *  for the shared demo user, which cannot keep preferences). The help
 *  page can show it again. */
export function Tour() {
  const { me, setMe } = useMe()
  const [hidden, setHidden] = useState(false)
  const [step, setStep] = useState(0)
  const [rects, setRects] = useState<Rect[]>([])
  const show = !hidden && !tourDone(me, browserStorage())
  const s = TOUR_STEPS[step]
  const credit = show && 'credit' in s && s.credit === true

  // the credit step opens the menu and the dialog while it is shown
  useEffect(() => {
    if (!credit) return
    signalCreditStep(true)
    return () => signalCreditStep(false)
  }, [credit])

  // the areas' places, after the first is scrolled into view; again on resize and scroll
  useEffect(() => {
    if (!show) return
    document.querySelector<HTMLElement>(s.targets[0])?.scrollIntoView({ block: 'nearest' })
    const update = () => setRects(measure(s.targets))
    // twice: the menu and the dialog of the credit step appear a frame later
    let second = 0
    const first = requestAnimationFrame(() => {
      update()
      second = requestAnimationFrame(update)
    })
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      cancelAnimationFrame(first)
      cancelAnimationFrame(second)
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [show, s.targets])

  if (!show || !me) return null

  function finish() {
    setHidden(true)
    noteTourDone(browserStorage(), me!.id, true)
    account.savePreferences({ tour_done: true }).then(setMe, () => {
      // the demo user (403) or an account service without the preference: this browser's note holds
    })
  }

  const last = step === TOUR_STEPS.length - 1
  const rect = rects[0] ?? null
  // the card below the first area when there is room, else above it
  const below = rect ? rect.top + rect.height + 180 < window.innerHeight : true
  const cardStyle = rect
    ? below
      ? { top: rect.top + rect.height + 12, left: Math.max(16, Math.min(rect.left, window.innerWidth - 336)) }
      : { top: Math.max(16, rect.top - 12), left: Math.max(16, Math.min(rect.left, window.innerWidth - 336)), transform: 'translateY(-100%)' }
    : { top: '30%', left: '50%', transform: 'translateX(-50%)' }

  return (
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {/* the page dimmed with a hole per outlined area */}
      <svg className="tour-dim" aria-hidden="true">
        <defs>
          <mask id="tour-holes">
            <rect width="100%" height="100%" fill="white" />
            {rects.map((r, i) => (
              <rect key={i} x={r.left} y={r.top} width={r.width} height={r.height} rx="6" fill="black" />
            ))}
          </mask>
        </defs>
        <rect width="100%" height="100%" mask="url(#tour-holes)" />
      </svg>
      {rects.map((r, i) => (
        <div key={i} className="tour-spot" style={r} />
      ))}
      <div className={`tour-card ${rect ? (below ? 'arrow-up' : 'arrow-down') : ''}`} style={cardStyle}>
        <p className="muted small">{t('tour.step', { n: step + 1, total: TOUR_STEPS.length })}</p>
        <h2 id="tour-title">{t(`tour.${s.key}.title`)}</h2>
        <p>{t(`tour.${s.key}`)}</p>
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
