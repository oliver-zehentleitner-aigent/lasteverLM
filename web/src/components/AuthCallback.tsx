import { useEffect, useState } from 'react'
import { account } from '../api/account'
import { setToken } from '../api/token'

interface Props {
  token: string
  onDone: () => void
}

/** Target of the mailed link: exchange the one-time token, store the JWT,
 *  go home. Runs once; a failure stays on screen rather than redirecting
 *  to a login page that would hide what went wrong. */
export function AuthCallback({ token, onDone }: Props) {
  const [error, setError] = useState<string | null>(token ? null : 'The link is missing its token.')

  useEffect(() => {
    let cancelled = false
    if (!token) return
    account
      .exchangeCallback(token)
      .then((r) => {
        if (cancelled) return
        setToken(r.jwt)
        onDone()
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [token, onDone])

  return (
    <main className="login">
      <h1>lasteverLM</h1>
      <section className="card">
        {error ? (
          <>
            <h2>Sign-in failed</h2>
            <p className="error">{error}</p>
            <a href="/">Request a new link</a>
          </>
        ) : (
          <p>Signing you in…</p>
        )}
      </section>
    </main>
  )
}
