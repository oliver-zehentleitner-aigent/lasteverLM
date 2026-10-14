import { useState } from 'react'
import type { AudioStyle, OutputKind, OutputOptions, OutputOptionsSpec } from '../api/types'
import { useMe } from '../hooks/useMe'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { AUDIO_STYLES, buildOptions, defaultValues, optionsFor, sampleLanguage, secondVoice, speedSteps, voiceGroups, type OptionValues } from '../lib/outputOptions'
import { OUTPUT_FORMS, createBlocker, tileNote } from '../lib/outputs'
import { VoiceSample } from './VoiceSample'
import { DecisionForm } from './DecisionForm'
import { decisionOptions, decisionProblem, defaultDecision, type DecisionValues } from '../lib/decision'
import { language, t } from '../i18n'

interface Props {
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
export function OutputTiles({ selected, hasReadySource, noneSelected, busy, onSelect, onCreate }: Props) {
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
  const problem = isDecision ? decisionProblem(dv, spec) : null
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
          {shown.includes('voice') && <VoiceSample voice={values.voice} speed={values.speed} language={sampleLanguage(values.language, spec, language())} />}
          {shown.includes('audio_voice_2') && values.style === 'conversation' && (
            <>
              <VoiceSelect label={t('tiles.voice2')} spec={spec} value={values.voice2} exclude={values.voice} onChange={(voice2) => set({ voice2 })} />
              <VoiceSample voice={values.voice2} speed={values.speed} language={sampleLanguage(values.language, spec, language())} />
            </>
          )}
        </div>
      )}
      <div className="create-row">
        {hint && <span className="muted small">{hint}</span>}
        <button
          type="button"
          disabled={busy || hint !== null}
          onClick={() =>
            selected &&
            onCreate(selected, {
              ...(spec && values ? buildOptions(selected, spec, values) : {}),
              ...(isDecision ? decisionOptions(dv, decisionKeys) : {}),
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
