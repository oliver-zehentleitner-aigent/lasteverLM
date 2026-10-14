import type { LibraryEntry } from '../api/types'
import { t, tn } from '../i18n'

export interface LibraryFilter {
  kind: LibraryEntry['kind'] | 'all'
  query: string
}

/** Entries matching a kind and a case-insensitive part of the name (or of
 *  the URL), in the server's order (newest first). */
export function filterLibrary(entries: readonly LibraryEntry[], f: LibraryFilter): LibraryEntry[] {
  const q = f.query.trim().toLowerCase()
  return entries.filter(
    (e) =>
      (f.kind === 'all' || e.kind === f.kind) &&
      (!q || e.name.toLowerCase().includes(q) || (e.url ?? '').toLowerCase().includes(q)),
  )
}

/** What "add from library" offers for a notebook: entries not in it yet. */
export function notInNotebook(entries: readonly LibraryEntry[], notebookId: string): LibraryEntry[] {
  return entries.filter((e) => !e.notebooks.some((n) => n.id === notebookId))
}

/** The confirmation before deleting an entry for good, naming every
 *  notebook it disappears from. */
export function deleteConfirmText(e: LibraryEntry): string {
  const where =
    e.notebooks.length === 0
      ? t('lib.inNoNotebook')
      : tn('lib.disappears', e.notebooks.length, { names: e.notebooks.map((n) => `"${n.title}"`).join(', ') })
  return t('lib.trashConfirm', { name: e.name, where })
}

/** When a trashed entry is purged, relative to now, in whole days. */
export function purgeIn(purgeAt: string, now: Date = new Date()): string {
  const ms = new Date(purgeAt).getTime() - now.getTime()
  if (!Number.isFinite(ms)) return purgeAt
  const days = Math.ceil(ms / 86_400_000)
  return days <= 0 ? t('lib.purgedToday') : tn('lib.purgedIn', days)
}

/** An address as a list shows it: host and path without the scheme, a
 *  leading "www." or a trailing slash; the full URL goes in the title. */
export function shortUrl(url: string): string {
  try {
    const u = new URL(url)
    const host = u.host.replace(/^www\./, '')
    const path = (u.pathname + u.search).replace(/\/$/, '')
    return host + path
  } catch {
    return url
  }
}

/** The confirmation for moving several entries to the trash, naming every
 *  notebook they disappear from (each once). */
export function bulkDeleteConfirmText(entries: Pick<LibraryEntry, 'notebooks'>[]): string {
  const titles = [...new Set(entries.flatMap((e) => e.notebooks.map((n) => n.title)))]
  const where = titles.length === 0 ? t('lib.bulkInNoNotebook') : tn('lib.bulkDisappears', titles.length, { names: titles.map((x) => `"${x}"`).join(', ') })
  return tn('lib.bulkTrashConfirm', entries.length, { where })
}

/** The title a notebook made from a selection starts with, never a raw
 *  address: the first file's name without its extension when there is a
 *  file among them, else the first web page's title (its name, when that
 *  is a title rather than the address) or, derived from the address, host
 *  and last path segment ("en.wikipedia.org · Dead reckoning"). */
export function notebookTitleFrom(entries: Pick<LibraryEntry, 'name' | 'kind' | 'url'>[]): string {
  const file = entries.find((e) => e.kind !== 'url')
  if (file) return file.name.replace(/\.[A-Za-z0-9]{1,5}$/, '')
  const page = entries[0]
  if (!page) return ''
  return isAddress(page.name) ? pageTitleFrom(page.url ?? page.name) : page.name
}

function isAddress(s: string): boolean {
  try {
    const { protocol } = new URL(s)
    return protocol === 'https:' || protocol === 'http:'
  } catch {
    return false
  }
}

/** "https://en.wikipedia.org/wiki/Dead_reckoning" -> "en.wikipedia.org ·
 *  Dead reckoning": the host without "www.", then the last path segment
 *  decoded, "_" and "-" as spaces, without a file extension. */
export function pageTitleFrom(url: string): string {
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return url
  }
  const host = u.host.replace(/^www\./, '')
  const last = u.pathname.split('/').filter(Boolean).pop()
  if (!last) return host
  let segment = last
  try {
    segment = decodeURIComponent(last)
  } catch {
    // a malformed escape stays as it is
  }
  const words = segment.replace(/\.[A-Za-z0-9]{1,5}$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return words ? `${host} · ${words}` : host
}
