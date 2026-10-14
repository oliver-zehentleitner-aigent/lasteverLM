import type { DecisionContent } from '../../api/types'
import { modelVersusEvidence, orderedDistribution, percent, scalePercent } from '../../lib/decision'
import { t } from '../../i18n'
import { ClaimMarks } from '../OutputProvenance'

/** A question weighed against the sources: the question, the decision
 *  model's answer drawn by type (a gauge for yes/no, a bar per option, a
 *  segmented scale with the weighted position), the verdict, whether the
 *  model and the evidence agree (a disagreement is shown, never hidden),
 *  the evidence on both sides with its markers, and what the sources do
 *  not say. Colours come from the tokens only. */
export function DecisionView({ content: c }: { content: DecisionContent }) {
  const versus = modelVersusEvidence(c)
  return (
    <div className="decision">
      <h2 className="decision-question">{c.question}</h2>
      <section className="verdict" aria-label={t('kind.decision')}>
        <Answer content={c} />
        <p className="verdict-text">{c.verdict_text}</p>
        <p className={`agreement agreement-${c.agreement}`} title={t('decision.agreementTitle')}>
          <span className="dot" aria-hidden="true" />
          {t(`decision.agreement.${c.agreement}`)}
          {versus && <span className="versus"> · {t('decision.versus', versus)}</span>}
        </p>
        {c.agreement_note && <p className="muted small agreement-note">{c.agreement_note}</p>}
      </section>
      <div className="evidence">
        <Evidence title={t('decision.for')} items={c.evidence_for ?? []} side="for" />
        <Evidence title={t('decision.against')} items={c.evidence_against ?? []} side="against" />
      </div>
      {(c.gaps ?? []).length > 0 && (
        <section className="gaps">
          <h3>{t('decision.gaps')}</h3>
          <ul>
            {c.gaps.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function Answer({ content: c }: { content: DecisionContent }) {
  const a = c.model_answer
  if ('probability_yes' in a) {
    const p = percent(a.probability_yes)
    return (
      <div className="gauge" role="img" aria-label={t('decision.gauge', { p })}>
        <div className="gauge-value">
          <strong>{p} %</strong> <span className="muted">{a.answer === 'yes' ? t('decision.yes') : t('decision.no')}</span>
        </div>
        <div className="gauge-track">
          <div className="gauge-fill" style={{ width: `${p}%` }} />
          <div className="gauge-mid" aria-hidden="true" />
        </div>
        <div className="gauge-ends muted small">
          <span>{t('decision.no')}</span>
          <span>{t('decision.yes')}</span>
        </div>
      </div>
    )
  }
  if ('legend' in a) {
    const dist = orderedDistribution(a.distribution, a.legend)
    return (
      <div className="scale">
        <div className="scale-bar" role="img" aria-label={t('decision.position', { level: a.level })}>
          {dist.map((d) => (
            <div key={d.label} className={d.label === a.level ? 'segment landed' : 'segment'} style={{ opacity: 0.35 + 0.65 * Math.min(1, d.p * 2) }} title={`${d.label}: ${percent(d.p)} %`} />
          ))}
          <div className="scale-marker" style={{ left: `${scalePercent(a.score, a.legend.length)}%` }} aria-hidden="true" />
        </div>
        <div className="scale-labels small" style={{ gridTemplateColumns: `repeat(${a.legend.length}, minmax(0, 1fr))` }}>
          {a.legend.map((l) => (
            <span key={l} className={l === a.level ? 'landed' : 'muted'}>
              {l}
            </span>
          ))}
        </div>
        <p className="muted small">
          {t('decision.position', { level: a.level })} · {t('decision.confidence', { p: percent(a.confidence) })}
        </p>
      </div>
    )
  }
  const order = c.model_answer && 'choice' in a ? Object.keys(a.distribution) : []
  const dist = orderedDistribution(a.distribution, order)
  return (
    <div className="choices">
      {dist.map((d) => (
        <div key={d.label} className={d.label === a.choice ? 'choice picked' : 'choice'}>
          <span className="choice-label">
            {d.label}
            {d.label === a.choice && <span className="muted small"> · {t('decision.selected')}</span>}
          </span>
          <span className="choice-track">
            <span className="choice-fill" style={{ width: `${percent(d.p)}%` }} />
          </span>
          <span className="choice-p">{percent(d.p)} %</span>
        </div>
      ))}
      <p className="muted small">{t('decision.confidence', { p: percent(a.confidence) })}</p>
    </div>
  )
}

function Evidence({ title, items, side }: { title: string; items: DecisionContent['evidence_for']; side: 'for' | 'against' }) {
  return (
    <section className={`evidence-col ${side}`}>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted small">{t('decision.noEvidence')}</p>
      ) : (
        <ul>
          {items.map((e, i) => (
            <li key={i}>
              {e.text} <ClaimMarks claim={e} text={e.text} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
