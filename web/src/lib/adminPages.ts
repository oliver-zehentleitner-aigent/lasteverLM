/** The admin panel's pages, in the order of the sub-navigation. The
 *  overview is the default and lives at /admin itself. */
export const ADMIN_PAGES = [
  { id: 'overview', label: 'Overview' },
  { id: 'users', label: 'Users' },
  { id: 'access', label: 'Access' },
  { id: 'credits', label: 'Credits' },
  { id: 'security', label: 'Security' },
  { id: 'visits', label: 'Visits' },
  { id: 'mail', label: 'Mail' },
] as const

export type AdminPageId = (typeof ADMIN_PAGES)[number]['id']

export function adminPath(page: AdminPageId): string {
  return page === 'overview' ? '/admin' : `/admin/${page}`
}

/** /admin and /admin/overview are the overview; an unknown page is null,
 *  so the caller can fall back instead of showing an empty panel. */
export function adminPageFromPath(pathname: string): AdminPageId | null {
  const m = /^\/admin(?:\/([^/]+))?\/?$/.exec(pathname)
  if (!m) return null
  if (!m[1]) return 'overview'
  return ADMIN_PAGES.find((p) => p.id === m[1])?.id ?? null
}
