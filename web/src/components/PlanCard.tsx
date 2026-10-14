import { useEffect, useRef, useState } from 'react'
import { rag } from '../api/rag'
import type { Plan, PlanStep } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { t } from '../i18n'
import { priceLabel } from '../lib/estimate'
import { planActive, planChangedWork, stepTarget } from '../lib/plan'

const POLL_MS = 2500

const price = (e: { min: number; max: number }) => priceLabel({ charge_cents_min: e.min, charge_cents_max: e.max })

interface Props {
  conversationId: string
  plan: Plan
  /** the plan as it stands now (a confirm, a cancel, a poll) */
  onChange: (plan: Plan) => void
  /** a step made something, or the plan ended: the lists and the messages reload */
  onWork: (ended: boolean) => void
  /** a done step's source or output, opened as a viewer tab */
  onOpen: (target: { type: 'source' | 'output'; id: string }) => void
}

/** An answer that is a plan: its steps numbered, each with its label and
 *  estimated price (an invalid one with its reason; it never runs), the
 *  total, and a web page's processing apart (ingest bills it at the price
 *  list's price). Run and Cancel while proposed; while running each step
 *  shows its state, polled every 2.5 s; a done step links to what it made. */
export function PlanCard({ conversationId, plan, onChange, onWork, onOpen }: Props) {
  const { busy, error, run } = useAsync()
  const [pollError, setPollError] = useState<string | null>(null)
  // the last state the card showed, to tell what a poll changed
  // and the callbacks, so a re-render (typing a question) does not restart the poll
  const current = useRef(plan)
  const handlers = useRef({ onChange, onWork })
  useEffect(() => {
    current.current = plan
    handlers.current = { onChange, onWork }
  }, [plan, onChange, onWork])
  const active = planActive(plan)
  const planId = plan.plan_id

  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => {
      rag.getPlan(conversationId, planId).then(
        (next) => {
          setPollError(null)
          const before = current.current
          handlers.current.onChange(next)
          if (planChangedWork(before, next)) handlers.current.onWork(!planActive(next))
        },
        (e: unknown) => setPollError(e instanceof Error ? e.message : String(e)),
      )
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [conversationId, planId, active])

  async function act(kind: 'confirm' | 'cancel') {
    const next = await run(() => (kind === 'confirm' ? rag.confirmPlan(conversationId, plan.plan_id) : rag.cancelPlan(conversationId, plan.plan_id)))
    if (next) {
      onChange(next)
      if (kind === 'cancel') onWork(true)
    }
  }

  return (
    <section className={`plan-card plan-${plan.status}`} aria-label={t('plan.title')}>
      <header className="plan-head">
        <strong>{t('plan.title')}</strong>
        <span className={`badge plan-status ${plan.status}`}>{t(`plan.status.${plan.status}`)}</span>
      </header>
      <ol className="plan-steps">
        {plan.steps.map((s) => (
          <Step key={s.n} step={s} proposed={plan.status === 'proposed'} onOpen={onOpen} />
        ))}
      </ol>
      <p className="plan-total small">
        {t('plan.total', { price: price(plan.estimate) })}
        {(plan.separate ?? []).map((x) => (
          <span key={x.n} className="muted" title={t('plan.separateTitle')}>
            {' · '}
            {t('plan.separate', { label: x.label, price: price(x) })}
          </span>
        ))}
      </p>
      {plan.status === 'proposed' && (
        <div className="plan-actions">
          <button type="button" disabled={busy || !plan.steps.some((s) => s.valid)} onClick={() => void act('confirm')}>
            {t('plan.run')}
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={() => void act('cancel')}>
            {t('plan.cancel')}
          </button>
        </div>
      )}
      {(error ?? pollError) && <p className="error small">{error ?? pollError}</p>}
    </section>
  )
}

function Step({ step: s, proposed, onOpen }: { step: PlanStep; proposed: boolean; onOpen: Props['onOpen'] }) {
  const target = stepTarget(s)
  return (
    <li className={`plan-step state-${s.state}${s.valid ? '' : ' invalid'}`}>
      <span className="plan-step-label">
        {target ? (
          <button type="button" className="link" title={t('plan.open')} onClick={() => onOpen(target)}>
            {s.result?.title || s.label}
          </button>
        ) : (
          s.label
        )}
      </span>
      {s.valid ? (
        <span className="muted small">
          {s.estimate.max > 0 ? price(s.estimate) : s.processing ? t('plan.seeBelow') : t('plan.free')}
        </span>
      ) : (
        <span className="error small">{s.invalid_reason ?? t('plan.invalid')}</span>
      )}
      {!proposed && s.valid && <span className={`badge step-state ${s.state}`}>{t(`plan.state.${s.state}`)}</span>}
      {s.error && <span className="error small step-error">{s.error}</span>}
      {s.state === 'done' && s.result?.sources && (
        <span className="muted small step-list">{s.result.sources.map((x) => x.name).join(', ') || t('plan.none')}</span>
      )}
      {s.state === 'done' && s.result?.outputs && (
        <span className="step-list small">
          {s.result.outputs.length === 0
            ? t('plan.none')
            : s.result.outputs.map((o, i) => (
                <span key={o.output_id}>
                  {i > 0 && ', '}
                  <button type="button" className="link" onClick={() => onOpen({ type: 'output', id: o.output_id })}>
                    {o.title}
                  </button>
                </span>
              ))}
        </span>
      )}
      {s.state === 'done' && s.result?.added && <span className="muted small step-list">{t('plan.added', { n: s.result.added.length, already: s.result.already?.length ?? 0 })}</span>}
    </li>
  )
}
