const KEY = 'lasteverlm.token'

/** The bearer token sent with every request. What it is (Supabase JWT or
 *  demo token) is an open family decision; the frontend only stores and
 *  forwards it. Kept in localStorage so a reload does not log the user out. */
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
