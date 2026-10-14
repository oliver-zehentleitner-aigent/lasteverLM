import { useState, type FormEvent } from 'react'
import { account } from '../api/account'
import { ApiError } from '../api/client'
import { setToken } from '../api/token'
import { useAsync } from '../hooks/useAsync'
import { SIGN_IN_CODE_LENGTH, checkCode, cleanCode } from '../lib/signInCode'
import { t } from '../i18n'

interface Props {
  onLoggedIn: () => void
}

/** Magic-link login: the mailed link, or the code printed under it in the
 *  same mail, pasted here (for another device than the one with the mail).
 *  Both are the same single-use token and go through the same exchange. */
export function LoginPage({ onLoggedIn }: Props) {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [refused, setRefused] = useState(false)
  const { busy, error, run } = useAsync()

  async function submit(e: FormEvent) {
    e.preventDefault()
    setRefused(false)
    const ok = await run(async () => {
      try {
        await account.requestLink(email.trim())
        return true
      } catch (err) {
        // a refused address is an answer, not a failure: no mail goes out
        if (err instanceof ApiError && err.code === 'not_allowed') {
          setRefused(true)
          return false
        }
        throw err
      }
    })
    if (ok) setSent(true)
  }

  return (
    <main className="login">
      <h1>lasteverLM</h1>
      <p className="tagline">
        <strong>{t('login.tagline')}</strong>
      </p>
      <p className="muted small">{t('login.taglineMore')}</p>

      {sent ? (
        <section className="card">
          <h2>{t('login.checkMail')}</h2>
          <p>{t('login.sentTo', { email })}</p>
          <button type="button" className="link" onClick={() => setSent(false)}>
            {t('login.otherAddress')}
          </button>
        </section>
      ) : (
        <form className="card" onSubmit={submit}>
          <h2>{t('login.signIn')}</h2>
          <label>
            {t('login.email')}
            <input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <button type="submit" disabled={busy || !email}>
            {busy ? t('login.sending') : t('login.send')}
          </button>
          {refused && <p className="error">{t('login.notAllowed')}</p>}
          {error && <p className="error">{error}</p>}
        </form>
      )}

      <CodeForm onLoggedIn={onLoggedIn} />
      <p className="muted small login-prices">
        <a href="/prices">{t('login.prices')}</a>
      </p>
    </main>
  )
}

/** The code from the mail, exchanged like the link's token. Checked for
 *  its format while typing; Continue waits for a well-formed code. */
function CodeForm({ onLoggedIn }: Props) {
  const [raw, setRaw] = useState('')
  const [shown, setShown] = useState(false)
  const { busy, error, run } = useAsync()
  const code = cleanCode(raw)
  const check = checkCode(code)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (check !== 'ok') return
    const jwt = await run(async () => {
      try {
        return (await account.exchangeCallback(code)).jwt
      } catch (err) {
        // the service answers 401 for a code that is unknown, used or expired
        if (err instanceof ApiError && err.status === 401) throw new Error(t('login.codeInvalid'))
        throw err
      }
    })
    if (jwt) {
      setToken(jwt)
      onLoggedIn()
    }
  }

  return (
    <details className="card demo">
      <summary>{t('login.haveToken')}</summary>
      <form onSubmit={submit}>
        <label>
          {t('login.token')}
          <span className="code-input">
            <input
              type={shown ? 'text' : 'password'}
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              autoComplete="one-time-code"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              aria-describedby="code-hint"
              aria-invalid={check === 'chars' || undefined}
            />
            <button
              type="button"
              className="icon"
              aria-pressed={shown}
              aria-label={shown ? t('login.hideCode') : t('login.showCode')}
              title={shown ? t('login.hideCode') : t('login.showCode')}
              onClick={() => setShown((v) => !v)}
            >
              👁
            </button>
          </span>
        </label>
        <p id="code-hint" className={check === 'chars' ? 'error small' : 'muted small'}>
          {check === 'chars'
            ? t('login.codeChars')
            : t('login.codeHint', { n: code.length, total: SIGN_IN_CODE_LENGTH })}
        </p>
        <button type="submit" disabled={busy || check !== 'ok'}>
          {t('login.continue')}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </details>
  )
}
