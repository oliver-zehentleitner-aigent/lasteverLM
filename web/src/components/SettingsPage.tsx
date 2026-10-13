import { useState, type FormEvent } from 'react'
import { account } from '../api/account'
import type { Preferences } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useMe } from '../hooks/useMe'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { voiceGroups } from '../lib/outputOptions'

const NOT_SET: Preferences = { ui_language: null, output_language: null, audio_voice: null, trash_days: null }
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
      <h1>Settings</h1>
      <form className="card" onSubmit={save}>
        <label>
          Interface language
          <select
            value={p.ui_language ?? ''}
            onChange={(e) => set({ ui_language: (e.target.value || null) as Preferences['ui_language'] })}
          >
            <option value="">Browser default</option>
            <option value="en">English</option>
            <option value="de">Deutsch</option>
          </select>
        </label>
        <label>
          Language of generated documents
          <select value={p.output_language ?? ''} onChange={(e) => set({ output_language: e.target.value || null })}>
            <option value="">Same as the sources</option>
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
          Voice for audio
          <select value={p.audio_voice ?? ''} onChange={(e) => set({ audio_voice: e.target.value || null })}>
            <option value="">Default{spec ? ` (${spec.audio.voices.find((v) => v.id === spec.audio.default_voice)?.label ?? spec.audio.default_voice})` : ''}</option>
            {spec &&
              voiceGroups(spec).map((g) => (
                <optgroup key={g.gender} label={g.gender === 'female' ? 'Female' : 'Male'}>
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
          Days in the trash
          <input
            type="number"
            min={1}
            max={365}
            step={1}
            placeholder={`${TRASH_DEFAULT} (default)`}
            value={p.trash_days ?? ''}
            onChange={(e) => set({ trash_days: e.target.value === '' ? null : Math.round(Number(e.target.value)) })}
          />
          <span className="muted small">How long a deleted library source can be restored. Empty means {TRASH_DEFAULT} days.</span>
        </label>
        {!spec && <p className="muted small">The lists of languages and voices could not be loaded; the stored values are kept.</p>}
        {error && <p className="error">{error}</p>}
        {saved && <p className="muted small">Saved.</p>}
        <div className="row">
          <button type="submit" disabled={busy || form === null}>
            Save
          </button>
        </div>
      </form>
    </main>
  )
}
