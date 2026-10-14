import type { DecisionType, OutputOptionsSpec } from '../api/types'
import { DECISION_TYPES, decisionLimits, type DecisionValues } from '../lib/decision'
import { t } from '../i18n'

interface Props {
  value: DecisionValues
  spec: OutputOptionsSpec | null
  onChange: (v: DecisionValues) => void
}

/** The decision kind's options under the tiles: the question (required,
 *  counted against rag's limit), how it is answered, and for a choice the
 *  options, for a scale the ordered levels, each list editable within its
 *  limits. */
export function DecisionForm({ value: v, spec, onChange }: Props) {
  const lim = decisionLimits(spec)
  const set = (patch: Partial<DecisionValues>) => onChange({ ...v, ...patch })
  const listKey = v.decisionType === 'choice' ? 'choices' : 'levels'
  const list = v.decisionType === 'choice' ? v.choices : v.levels
  const { min, max } = v.decisionType === 'choice' ? lim.choices : lim.levels

  return (
    <div className="decision-form">
      <label className="question">
        {t('decision.question')}
        <textarea
          rows={3}
          required
          maxLength={lim.question_max_chars}
          placeholder={t('decision.questionPlaceholder')}
          value={v.question}
          onChange={(e) => set({ question: e.target.value })}
        />
        <span className="muted small count">{t('decision.chars', { n: v.question.trim().length, max: lim.question_max_chars })}</span>
      </label>
      <label>
        {t('decision.type')}
        <select value={v.decisionType} onChange={(e) => set({ decisionType: e.target.value as DecisionType })}>
          {DECISION_TYPES.filter((d) => lim.types.includes(d)).map((d) => (
            <option key={d} value={d}>
              {t(`decision.type.${d}`)}
            </option>
          ))}
        </select>
      </label>
      {v.decisionType !== 'yes_no' && (
        <fieldset className="plain decision-list">
          <legend>{v.decisionType === 'choice' ? t('decision.choices') : t('decision.levels')}</legend>
          <ol>
            {list.map((item, i) => (
              <li key={i}>
                <input
                  value={item}
                  aria-label={v.decisionType === 'choice' ? t('decision.optionN', { n: i + 1 }) : t('decision.levelN', { n: i + 1 })}
                  onChange={(e) => set({ [listKey]: list.map((x, k) => (k === i ? e.target.value : x)) })}
                />
                <button
                  type="button"
                  className="icon"
                  disabled={list.length <= min}
                  title={t('decision.remove', { label: item || String(i + 1) })}
                  aria-label={t('decision.remove', { label: item || String(i + 1) })}
                  onClick={() => set({ [listKey]: list.filter((_, k) => k !== i) })}
                >
                  ×
                </button>
              </li>
            ))}
          </ol>
          <button type="button" className="secondary small" disabled={list.length >= max} onClick={() => set({ [listKey]: [...list, ''] })}>
            {t('decision.add')}
          </button>
        </fieldset>
      )}
    </div>
  )
}
