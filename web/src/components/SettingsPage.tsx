import { useState, type FormEvent } from 'react'
import { account } from '../api/account'
import type { Preferences } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useMe } from '../hooks/useMe'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { CAPTURE_MODES } from '../lib/capture'
import { voiceGroups } from '../lib/outputOptions'
import { t } from '../i18n'

const NOT_SET: Preferences = { ui_language: null, output_language: null, audio_voice: null, trash_days: null, pdf_capture: null }
const TRASH_DEFAULT = 14

/** /settings: the user's preferences, preselected in every menu they
 *  apply to. Saved together; an empty choice clears the value (null). */
export function SettingsPage() {
  const { me, setMe } = useMe()
  const spec = useOutputOptions()
  const stored = me?.preferences ?? NOT_SET
  const [form, setForm] = useState<Preferences | null>(null)
  const [saved, setSaved] = useState(false)
  const { busy, error, run } = useAsync()
  const p = form ?? stored

  async function save(e: FormEvent) {
    e.preventDefault()
    setSaved(false)
    const user = await run(() => account.savePreferences(p))
    if (user) {
      setMe(user)
      setForm(null)
      setSaved(true)
    }
  }

  const set = (patch: Partial<Preferences>) => {
    setSaved(false)
    setForm({ ...p, ...patch })
  }

  return (
    <main className="settings">
      <h1>{t('set.title')}</h1>
      <form className="card" onSubmit={save}>
        <label>
          {t('set.uiLanguage')}
          <select
            value={p.ui_language ?? ''}
            onChange={(e) => set({ ui_language: (e.target.value || null) as Preferences['ui_language'] })}
          >
            <option value="">{t('set.browserDefault')}</option>
            <option value="en">English</option>
            <option value="de">Deutsch</option>
          </select>
        </label>
        <label>
          {t('set.outputLanguage')}
          <select value={p.output_language ?? ''} onChange={(e) => set({ output_language: e.target.value || null })}>
            <option value="">{t('tiles.sameAsSources')}</option>
            {spec?.languages.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
            {/* a stored value the list does not offer stays visible */}
            {p.output_language && spec && !spec.languages.some((l) => l.code === p.output_language) && (
              <option value={p.output_language}>{p.output_language}</option>
            )}
          </select>
        </label>
        <label>
          {t('set.voice')}
          <select value={p.audio_voice ?? ''} onChange={(e) => set({ audio_voice: e.target.value || null })}>
            <option value="">
              {spec
                ? t('set.defaultNamed', { name: spec.audio.voices.find((v) => v.id === spec.audio.default_voice)?.label ?? spec.audio.default_voice })
                : t('set.default')}
            </option>
            {spec &&
              voiceGroups(spec).map((g) => (
                <optgroup key={g.gender} label={g.gender === 'female' ? t('tiles.female') : t('tiles.male')}>
                  {g.voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            {p.audio_voice && spec && !spec.audio.voices.some((v) => v.id === p.audio_voice) && (
              <option value={p.audio_voice}>{p.audio_voice}</option>
            )}
          </select>
        </label>
        <label>
          {t('set.pdf')}
          <select
            value={p.pdf_capture ?? ''}
            onChange={(e) => set({ pdf_capture: (e.target.value || null) as Preferences['pdf_capture'] })}
          >
            <option value="">{t('set.pdfDefault')}</option>
            {CAPTURE_MODES.map((m) => (
              <option key={m.mode} value={m.mode}>
                {m.label}: {m.explain}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('set.trashDays')}
          <input
            type="number"
            min={1}
            max={365}
            step={1}
            placeholder={t('set.trashDefault', { n: TRASH_DEFAULT })}
            value={p.trash_days ?? ''}
            onChange={(e) => set({ trash_days: e.target.value === '' ? null : Math.round(Number(e.target.value)) })}
          />
          <span className="muted small">{t('set.trashHint', { n: TRASH_DEFAULT })}</span>
        </label>
        {!spec && <p className="muted small">{t('set.noSpec')}</p>}
        {error && <p className="error">{error}</p>}
        {saved && <p className="muted small">{t('common.saved')}</p>}
        <div className="row">
          <button type="submit" disabled={busy || form === null}>
            {t('common.save')}
          </button>
        </div>
      </form>
    </main>
  )
}
