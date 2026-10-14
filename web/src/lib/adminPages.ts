import { t } from '../i18n'

/** The admin panel's pages, in the order of the sub-navigation. The
 *  overview is the default and lives at /admin itself. */
export const ADMIN_PAGES = [
  { id: 'overview', get label() { return t('admin.page.overview') } },
  { id: 'finance', get label() { return t('admin.page.finance') } },
  { id: 'users', get label() { return t('admin.page.users') } },
  { id: 'access', get label() { return t('admin.page.access') } },
  { id: 'security', get label() { return t('admin.page.security') } },
  { id: 'visits', get label() { return t('admin.page.visits') } },
  { id: 'mail', get label() { return t('admin.page.mail') } },
  { id: 'system', get label() { return t('admin.page.system') } },
] as const

export type AdminPageId = (typeof ADMIN_PAGES)[number]['id']

export function adminPath(page: AdminPageId): string {
  return page === 'overview' ? '/admin' : `/admin/${page}`
}

/** /admin and /admin/overview are the overview; an unknown page is null,
 *  so the caller can fall back instead of showing an empty panel. Finance
 *  has pages of its own under /admin/finance/; the old /admin/credits is
 *  its vouchers page. */
export function adminPageFromPath(pathname: string): AdminPageId | null {
  if (/^\/admin\/credits\/?$/.test(pathname)) return 'finance'
  if (/^\/admin\/finance(?:\/[^/]+)?\/?$/.test(pathname)) return financePageFromPath(pathname) ? 'finance' : null
  const m = /^\/admin(?:\/([^/]+))?\/?$/.exec(pathname)
  if (!m) return null
  if (!m[1]) return 'overview'
  return ADMIN_PAGES.find((p) => p.id === m[1])?.id ?? null
}

/** Finance's pages, in the order of its sub-navigation; costs is the default. */
export const FINANCE_PAGES = [
  { id: 'costs', get label() { return t('fin.page.costs') } },
  { id: 'prices', get label() { return t('fin.page.prices') } },
  { id: 'revenue', get label() { return t('fin.page.revenue') } },
  { id: 'infrastructure', get label() { return t('fin.page.infrastructure') } },
  { id: 'vouchers', get label() { return t('fin.page.vouchers') } },
] as const

export type FinancePageId = (typeof FINANCE_PAGES)[number]['id']

export function financePath(page: FinancePageId): string {
  return page === 'costs' ? '/admin/finance' : `/admin/finance/${page}`
}

/** The finance page of a path; null when it is not one. */
export function financePageFromPath(pathname: string): FinancePageId | null {
  if (/^\/admin\/credits\/?$/.test(pathname)) return 'vouchers'
  const m = /^\/admin\/finance(?:\/([^/]+))?\/?$/.exec(pathname)
  if (!m) return null
  if (!m[1]) return 'costs'
  return FINANCE_PAGES.find((p) => p.id === m[1])?.id ?? null
}
