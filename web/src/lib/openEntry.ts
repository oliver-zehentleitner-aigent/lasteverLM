import type { LibraryEntry } from '../api/types'

/** Where "open" takes a library entry, in a new tab: a web page to its
 *  address, an upload (PDF, text, image) to its presigned `preview_url`.
 *  Only http(s) addresses qualify, so a stored `javascript:` or `data:`
 *  URL never becomes a link; null when there is nothing to open (yet). */
export function openTarget(e: Pick<LibraryEntry, 'kind' | 'url' | 'preview_url'>): string | null {
  const href = e.kind === 'url' ? e.url : e.preview_url
  if (!href) return null
  try {
    const { protocol } = new URL(href)
    return protocol === 'https:' || protocol === 'http:' ? href : null
  } catch {
    return null
  }
}
