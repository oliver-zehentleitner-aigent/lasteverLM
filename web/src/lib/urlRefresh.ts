import type { Source } from '../api/types'

/** The pages to fetch again, of those still selected: a page turned off
 *  or removed drops out. Library ids, as rag's `url_refresh` takes them. */
export function keptRefresh(refresh: ReadonlySet<string>, pages: readonly Pick<Source, 'id' | 'library_id'>[]): string[] {
  const ids = new Set(pages.map((s) => s.library_id ?? s.id))
  return [...refresh].filter((x) => ids.has(x))
}
