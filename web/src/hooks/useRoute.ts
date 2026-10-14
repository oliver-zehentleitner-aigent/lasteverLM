import { useCallback, useEffect, useState } from 'react'
import { adminPageFromPath, type AdminPageId } from '../lib/adminPages'

/** A handful of routes does not justify a router dependency. Path-based so the
 *  magic-link callback URL is a plain /auth/callback?token=..., which nginx
 *  rewrites to index.html. */
export type Route =
  | { name: 'home' }
  | { name: 'auth-callback'; token: string }
  | { name: 'admin'; page: AdminPageId }
  | { name: 'library' }
  | { name: 'settings' }
  | { name: 'prices' }
  | { name: 'shared'; token: string }
  | { name: 'shared-notebook'; token: string }

/** Pure, so the route table is unit-tested without a browser. */
export function parseRoute(loc: Pick<Location, 'pathname' | 'search'>): Route {
  if (loc.pathname === '/auth/callback') {
    return { name: 'auth-callback', token: new URLSearchParams(loc.search).get('token') ?? '' }
  }
  if (loc.pathname === '/admin' || loc.pathname.startsWith('/admin/')) {
    // an unknown admin page opens the overview rather than the workspace
    return { name: 'admin', page: adminPageFromPath(loc.pathname) ?? 'overview' }
  }
  if (loc.pathname === '/library' || loc.pathname === '/library/') return { name: 'library' }
  if (loc.pathname === '/settings' || loc.pathname === '/settings/') return { name: 'settings' }
  // public, like the share pages: no login needed
  if (loc.pathname === '/prices' || loc.pathname === '/prices/') return { name: 'prices' }
  const sharedNotebook = /^\/shared\/notebook\/([^/]+)$/.exec(loc.pathname)
  if (sharedNotebook) return { name: 'shared-notebook', token: decodeURIComponent(sharedNotebook[1]) }
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
