import { Suspense, lazy, useState } from 'react'
import type { Audience, ChartCandidate, AudioStyle, Difficulty, OutputKind, OutputOptions, OutputOptionsSpec, ReportLength, ReportStyle } from '../api/types'
import { useMe } from '../hooks/useMe'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { AUDIO_STYLES, INSTRUCTIONS_MAX, buildOptions, defaultValues, optionsFor, sampleLanguage, secondVoice, speedSteps, voiceGroups, type OptionValues } from '../lib/outputOptions'
import { OUTPUT_FORMS, createBlocker, tileNote } from '../lib/outputs'
import { VoiceSample } from './VoiceSample'
import { RedeemLink } from './RedeemLink'

// recharts comes with it, loaded only when the chart kind is picked
const ChartProposals = lazy(() => import('./ChartProposals'))
import { DecisionForm } from './DecisionForm'
import { decisionOptions, decisionProblem, defaultDecision, type DecisionValues } from '../lib/decision'
import { language, t } from '../i18n'

interface Props {
  /** for the chart kind's proposal call */
  notebookId: string
  selected: OutputKind | null
  hasReadySource: boolean
  /** every source is turned off in the list */
  noneSelected: boolean
  busy: boolean
  onSelect: (kind: OutputKind) => void
  onCreate: (kind: OutputKind, options: OutputOptions) => void
}

/** The output formats as tiles under the sources. A click (or Enter on a
 *  focused tile) only selects one and shows that format's options (language,
 *  and voice and speed for audio), preset from the user's preferences; the
 *  Create button below starts the job, and says why when it cannot yet. */
export function OutputTiles({ notebookId, selected, hasReadySource, noneSelected, busy, onSelect, onCreate }: Props) {
  const blocker = createBlocker(selected, hasReadySource, noneSelected)
  const spec = useOutputOptions()
  const { me } = useMe()
  const [chosen, setChosen] = useState<OptionValues | null>(null)
  const values = chosen ?? (spec ? defaultValues(spec, me?.preferences) : null)
  const shown = selected && spec ? optionsFor(selected, spec) : []
  const set = (patch: Partial<OptionValues>) => values && setChosen({ ...values, ...patch })
  // the decision's question and lists, kept apart from the shared options
  const [decision, setDecision] = useState<DecisionValues | null>(null)
  const dv = decision ?? defaultDecision(spec)
  const isDecision = selected === 'decision'
  // a rag that predates the catalogue entry still gets the contract's keys
  const decisionKeys = spec?.kinds.decision ?? ['language', 'question', 'decision_type', 'choices', 'levels']
  // the chart kind: the proposed charts ticked for Create
  const isChart = selected === 'chart'
  const [charts, setCharts] = useState<ChartCandidate[]>([])
  const problem = isDecision ? decisionProblem(dv, spec) : isChart && charts.length === 0 ? t('chartOut.needPick') : null
  // without credit sources still go in (and wait); outputs cannot be made
  const noCredit = me !== null && me !== undefined && me.balance_cents <= 0
  const hint = blocker ?? problem
  return (
    <section className="tiles">
      <h2>{t('tiles.title')}</h2>
      <div className="tile-grid" role="radiogroup" aria-label={t('tiles.title')}>
        {OUTPUT_FORMS.map((f) => (
          <button
            key={f.kind}
            type="button"
            role="radio"
            aria-checked={f.kind === selected}
            className={f.kind === selected ? 'tile selected' : 'tile'}
            disabled={!f.available}
            title={tileNote(f)}
            onClick={() => onSelect(f.kind)}
          >
            <strong>{f.label}</strong>
            <span className="muted small">{tileNote(f)}</span>
          </button>
        ))}
      </div>
      {isDecision && <DecisionForm value={dv} spec={spec} onChange={setDecision} />}
      {spec && values && shown.length > 0 && (
        <div className="output-options">
          {shown.includes('language') && (
            <label>
              {t('tiles.language')}
              <select value={values.language} onChange={(e) => set({ language: e.target.value })}>
                <option value="">{t('tiles.sameAsSources')}</option>
                {spec.languages.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {shown.includes('audio_style') && (
            <label>
              {t('tiles.style')}
              <select value={values.style} onChange={(e) => set({ style: e.target.value as AudioStyle })}>
                {AUDIO_STYLES.map((s) => (
                  <option key={s} value={s}>
                    {t(`audioStyle.${s}`)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {shown.includes('voice') && (
            <VoiceSelect
              label={t('tiles.voice')}
              spec={spec}
              value={values.voice}
              // the two speakers of a conversation never share a voice (rag refuses that)
              onChange={(voice) => set({ voice, voice2: voice === values.voice2 ? secondVoice(spec, voice) : values.voice2 })}
            />
          )}
          {shown.includes('speed') && (
            <label>
              {t('tiles.speed')}
              <select value={values.speed} onChange={(e) => set({ speed: Number(e.target.value) })}>
                {speedSteps(spec).map((v) => (
                  <option key={v} value={v}>
                    {v}×
                  </option>
                ))}
              </select>
            </label>
          )}
          {shown.includes('report_style') && spec.report && (
            <label>
              {t('opt.reportStyle')}
              <select value={values.reportStyle} onChange={(e) => set({ reportStyle: e.target.value as ReportStyle })}>
                {spec.report.styles.map((v) => (
                  <option key={v} value={v}>
                    {t(`opt.reportStyle.${v}`)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {shown.includes('length') && spec.report && (
            <label>
              {t('opt.length')}
              <select value={values.length} onChange={(e) => set({ length: e.target.value as ReportLength })}>
                {spec.report.lengths.map((v) => (
                  <option key={v} value={v}>
                    {t(`opt.length.${v}`)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {shown.includes('question_count') && spec.quiz && (
            <label>
              {t('opt.questionCount')}
              <input
                type="number"
                className="narrow"
                min={spec.quiz.question_count.min}
                max={spec.quiz.question_count.max}
                value={values.questionCount}
                onChange={(e) => {
                  const n = Math.round(Number(e.target.value))
                  const { min, max } = spec.quiz!.question_count
                  if (Number.isFinite(n)) set({ questionCount: Math.min(max, Math.max(min, n)) })
                }}
              />
            </label>
          )}
          {shown.includes('difficulty') && spec.quiz && (
            <label>
              {t('opt.difficulty')}
              <select value={values.difficulty} onChange={(e) => set({ difficulty: e.target.value as Difficulty })}>
                {spec.quiz.difficulties.map((v) => (
                  <option key={v} value={v}>
                    {t(`opt.difficulty.${v}`)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {shown.includes('audience') && spec.quiz && (
            <label>
              {t('opt.audience')}
              <select value={values.audience} onChange={(e) => set({ audience: e.target.value as Audience })}>
                {spec.quiz.audiences.map((v) => (
                  <option key={v} value={v}>
                    {t(`opt.audience.${v}`)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {shown.includes('voice') && <VoiceSample voice={values.voice} speed={values.speed} language={sampleLanguage(values.language, spec, language())} />}
          {shown.includes('audio_voice_2') && values.style === 'conversation' && (
            <>
              <VoiceSelect label={t('tiles.voice2')} spec={spec} value={values.voice2} exclude={values.voice} onChange={(voice2) => set({ voice2 })} />
              <VoiceSample voice={values.voice2} speed={values.speed} language={sampleLanguage(values.language, spec, language())} />
            </>
          )}
          {shown.includes('instructions') && (
            <label className="instructions">
              {t('opt.instructions')}
              <textarea
                rows={2}
                maxLength={spec.instructions?.max_chars ?? INSTRUCTIONS_MAX}
                placeholder={t('opt.instructionsPlaceholder')}
                value={values.instructions}
                onChange={(e) => set({ instructions: e.target.value })}
              />
              <span className="muted small">{t('opt.instructionsHint', { n: values.instructions.length, max: spec.instructions?.max_chars ?? INSTRUCTIONS_MAX })}</span>
            </label>
          )}
        </div>
      )}
      {isChart && values && (
        <Suspense fallback={<p className="muted small">{t('common.loading')}</p>}>
          <ChartProposals notebookId={notebookId} spec={spec} instructions={values.instructions} picked={charts} onPick={setCharts} />
        </Suspense>
      )}
      <div className="create-row">
        {noCredit ? (
          <span className="muted small">
            {t('tiles.noCredit')} <RedeemLink />
          </span>
        ) : (
          hint && <span className="muted small">{hint}</span>
        )}
        <button
          type="button"
          disabled={busy || hint !== null || noCredit}
          onClick={() =>
            selected &&
            onCreate(selected, {
              ...(spec && values ? buildOptions(selected, spec, values) : {}),
              ...(isDecision ? decisionOptions(dv, decisionKeys) : {}),
              ...(isChart ? { charts } : {}),
            })
          }
        >
          {t('tiles.create')}
        </button>
      </div>
    </section>
  )
}

/** The voices grouped female and male; `exclude` leaves one out (the
 *  first speaker's, in the second voice's select). */
function VoiceSelect({ label, spec, value, exclude, onChange }: { label: string; spec: OutputOptionsSpec; value: string; exclude?: string; onChange: (voice: string) => void }) {
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {voiceGroups(spec).map((g) => (
          <optgroup key={g.gender} label={g.gender === 'female' ? t('tiles.female') : t('tiles.male')}>
            {g.voices
              .filter((v) => v.id !== exclude)
              .map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
    </label>
  )
}
