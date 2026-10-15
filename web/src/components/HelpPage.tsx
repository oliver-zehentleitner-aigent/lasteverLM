import { useState } from 'react'
import { account } from '../api/account'
import { ingest } from '../api/ingest'
import { writeLastNotebook } from '../lib/lastNotebook'
import { starterCopyRefusal } from '../lib/starterCopy'
import { useMe } from '../hooks/useMe'
import { t, type MessageKey } from '../i18n'
import { browserStorage } from '../lib/layout'
import { noteTourDone } from '../lib/tour'

const STEPS = ['sources', 'select', 'ask', 'format', 'create', 'evidence'] as const

/** /help: how a notebook is used, in six steps, and the introduction to
 *  start again. */
export function HelpPage() {
  const { me, setMe } = useMe()
  const [copying, setCopying] = useState(false)
  const [copyError, setCopyError] = useState<string | null>(null)

  /** A fresh copy of the current starter, free; it opens at once and its
   *  outputs follow (the notebook asks for them until they are there).
   *  With a starter copy still there, it asks before making another. */
  async function recreateStarter(force = false) {
    setCopying(true)
    setCopyError(null)
    try {
      const nb = await ingest.copyStarter(force)
      writeLastNotebook(nb.id)
      window.location.assign('/')
    } catch (err) {
      const r = starterCopyRefusal(err)
      if (r.kind === 'exists') {
        if (confirm(t('help.starter.exists'))) {
          void recreateStarter(true)
          return
        }
      } else setCopyError(r.text)
    }
    setCopying(false)
  }

  /** Clears the account's flag and this browser's note, then opens the
   *  notebook, where the introduction starts. */
  async function showTourAgain() {
    if (!me) return
    noteTourDone(browserStorage(), me.id, false)
    try {
      setMe(await account.savePreferences({ tour_done: false }))
    } catch {
      // the demo user cannot keep preferences; clearing this browser's note is enough there
    }
    window.location.assign('/')
  }

  return (
    <main className="help">
      <h1>{t('help.title')}</h1>
      <ol className="help-steps">
        {STEPS.map((s) => (
          <li key={s}>
            <strong>{t(`help.step.${s}` as MessageKey)}</strong>
            <p>{t(`help.step.${s}.text` as MessageKey)}</p>
          </li>
        ))}
      </ol>
      <section className="card help-actions">
        <button type="button" className="secondary" onClick={() => void showTourAgain()}>
          {t('set.tourAgain')}
        </button>
        <button type="button" className="secondary" disabled={copying} onClick={() => void recreateStarter()}>
          {copying ? t('help.starter.copying') : t('help.starter.recreate')}
        </button>
        <span className="muted small">{t('help.starter.hint')}</span>
        {copyError && <p className="error small">{copyError}</p>}
      </section>
    </main>
  )
}
