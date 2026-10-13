import { useState } from 'react'
import type { OutputKind, OutputOptions } from '../api/types'
import { useMe } from '../hooks/useMe'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { buildOptions, defaultValues, optionsFor, speedSteps, voiceGroups, type OptionValues } from '../lib/outputOptions'
import { OUTPUT_FORMS, createBlocker, tileNote } from '../lib/outputs'
import { t } from '../i18n'

interface Props {
  selected: OutputKind | null
  hasReadySource: boolean
  busy: boolean
  onSelect: (kind: OutputKind) => void
  onCreate: (kind: OutputKind, options: OutputOptions) => void
}

/** The output formats as tiles under the sources. A click (or Enter on a
 *  focused tile) only selects one and shows that format's options (language,
 *  and voice and speed for audio), preset from the user's preferences; the
 *  Create button below starts the job, and says why when it cannot yet. */
export function OutputTiles({ selected, hasReadySource, busy, onSelect, onCreate }: Props) {
  const blocker = createBlocker(selected, hasReadySource)
  const spec = useOutputOptions()
  const { me } = useMe()
  const [chosen, setChosen] = useState<OptionValues | null>(null)
  const values = chosen ?? (spec ? defaultValues(spec, me?.preferences) : null)
  const shown = selected && spec ? optionsFor(selected, spec) : []
  const set = (patch: Partial<OptionValues>) => values && setChosen({ ...values, ...patch })
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
          {shown.includes('voice') && (
            <label>
              {t('tiles.voice')}
              <select value={values.voice} onChange={(e) => set({ voice: e.target.value })}>
                {voiceGroups(spec).map((g) => (
                  <optgroup key={g.gender} label={g.gender === 'female' ? t('tiles.female') : t('tiles.male')}>
                    {g.voices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
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
        </div>
      )}
      <div className="create-row">
        {blocker && <span className="muted small">{blocker}</span>}
        <button type="button" disabled={busy || blocker !== null} onClick={() => selected && onCreate(selected, spec && values ? buildOptions(selected, spec, values) : {})}>
          {t('tiles.create')}
        </button>
      </div>
    </section>
  )
}
