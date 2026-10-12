const KEY = 'lasteverlm.token'

/** The bearer token sent with every request: the JWT the account service
 *  issues after a magic link, or the demo token in development. The
 *  frontend only stores and forwards it. Kept in localStorage so a reload
 *  does not log the user out. */
export function getToken(): string {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(KEY, token)
    else localStorage.removeItem(KEY)
  } catch {
    // storage unavailable (private mode); the token lives for this page load only
  }
}
