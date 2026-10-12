import { useCallback, useEffect, useState } from 'react'

/** Four routes do not justify a router dependency. Path-based so the
 *  magic-link callback URL is a plain /auth/callback?token=..., which nginx
 *  rewrites to index.html. */
export type Route =
  | { name: 'home' }
  | { name: 'auth-callback'; token: string }
  | { name: 'admin' }
  | { name: 'shared'; token: string }

/** Pure, so the route table is unit-tested without a browser. */
export function parseRoute(loc: Pick<Location, 'pathname' | 'search'>): Route {
  if (loc.pathname === '/auth/callback') {
    return { name: 'auth-callback', token: new URLSearchParams(loc.search).get('token') ?? '' }
  }
  if (loc.pathname === '/admin') return { name: 'admin' }
  const shared = /^\/s\/([^/]+)$/.exec(loc.pathname)
  if (shared) return { name: 'shared', token: decodeURIComponent(shared[1]) }
  return { name: 'home' }
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location))

  useEffect(() => {
    const onPop = () => setRoute(parseRoute(window.location))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((path: string) => {
    window.history.pushState(null, '', path)
    setRoute(parseRoute(window.location))
  }, [])

  return { route, navigate }
}
