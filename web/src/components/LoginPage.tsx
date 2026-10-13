import { useState, type FormEvent } from 'react'
import { account } from '../api/account'
import { ApiError } from '../api/client'
import { setToken } from '../api/token'
import { useAsync } from '../hooks/useAsync'

interface Props {
  onLoggedIn: () => void
}

/** Magic-link login. The demo token path exists so the stack can be tested
 *  before mail delivery works; it is the same Bearer header either way. */
export function LoginPage({ onLoggedIn }: Props) {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [refused, setRefused] = useState(false)
  const [demo, setDemo] = useState('')
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

  function useDemo(e: FormEvent) {
    e.preventDefault()
    if (!demo.trim()) return
    setToken(demo.trim())
    onLoggedIn()
  }

  return (
    <main className="login">
      <h1>lasteverLM</h1>
      <p className="muted">Provide documents, ask questions, get cited answers.</p>

      {sent ? (
        <section className="card">
          <h2>Check your mail</h2>
          <p>
            A sign-in link went to <strong>{email}</strong>. Open it in this browser.
          </p>
          <button type="button" className="link" onClick={() => setSent(false)}>
            Use another address
          </button>
        </section>
      ) : (
        <form className="card" onSubmit={submit}>
          <h2>Sign in</h2>
          <label>
            E-mail
            <input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <button type="submit" disabled={busy || !email}>
            {busy ? 'Sending…' : 'Send sign-in link'}
          </button>
          {refused && <p className="error">This address has no access to lasteverLM.</p>}
          {error && <p className="error">{error}</p>}
        </form>
      )}

      <details className="card demo">
        <summary>Have an access token?</summary>
        <form onSubmit={useDemo}>
          <label>
            Token
            <input type="password" value={demo} onChange={(e) => setDemo(e.target.value)} autoComplete="off" />
          </label>
          <button type="submit" disabled={!demo.trim()}>
            Continue
          </button>
        </form>
      </details>
    </main>
  )
}
