import { useEffect } from 'react'
import type { Route } from '../hooks/useRoute'
import { t } from '../i18n'
import { ADMIN_PAGES, FINANCE_PAGES, financePageFromPath } from './adminPages'

const APP = 'lasteverLM'
/** a title part longer than this is cut, so the app's name stays visible in a tab */
export const TITLE_PART_MAX = 60

/** The browser tab's title: the parts from the most specific, each
 *  trimmed and cut to a sensible length, empty ones left out, then the
 *  app's name: "Report · My notebook · lasteverLM". Pure, so it is tested;
 *  `document.title` takes it as text, never as markup. */
export function docTitle(...parts: (string | null | undefined)[]): string {
  const kept = parts
    .map((p) => (p ?? '').replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .map((p) => (p.length > TITLE_PART_MAX ? `${p.slice(0, TITLE_PART_MAX - 1).trimEnd()}…` : p))
  return [...kept, APP].join(' · ')
}

/** Sets the browser tab's title while the caller shows; null leaves it to another. */
export function useDocumentTitle(title: string | null): void {
  useEffect(() => {
    if (title !== null) document.title = title
  }, [title])
}

/** The title of an app page by its route, in the interface language: the
 *  page's name ("Settings", "Admin · Finance · Costs"); null for the pages
 *  that name themselves from what they show (the workspace with its
 *  notebook, the shared pages). */
export function routeTitle(route: Route, pathname: string, signedIn: boolean): string | null {
  if (!signedIn && route.name !== 'prices' && route.name !== 'shared' && route.name !== 'shared-notebook') return docTitle()
  switch (route.name) {
    case 'library':
      return docTitle(t('header.library'))
    case 'settings':
      return docTitle(t('header.settings'))
    case 'prices':
      return docTitle(t('header.prices'))
    case 'credits':
      return docTitle(t('credit.title'))
    case 'admin': {
      const page = ADMIN_PAGES.find((p) => p.id === route.page)?.label
      const finance = route.page === 'finance' ? FINANCE_PAGES.find((p) => p.id === (financePageFromPath(pathname) ?? 'revenue'))?.label : null
      return docTitle(t('header.admin'), page, finance)
    }
    case 'auth-callback':
      return docTitle()
    default:
      return null
  }
}
