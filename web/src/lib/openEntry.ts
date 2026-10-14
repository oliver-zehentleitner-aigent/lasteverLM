import type { LibraryEntry, Source } from '../api/types'

/** Where "open" takes a library entry, in a new tab: a web page to its
 *  address, an upload (PDF, text, image) to its presigned `preview_url`.
 *  Only http(s) addresses qualify, so a stored `javascript:` or `data:`
 *  URL never becomes a link; null when there is nothing to open (yet). */
export function openTarget(e: Pick<LibraryEntry, 'kind' | 'url' | 'preview_url'>): string | null {
  return httpOnly(e.kind === 'url' ? e.url : e.preview_url)
}

/** Where "open in source" on a citation takes a notebook source, in a new
 *  tab: its `preview_url` (a web page's address, an upload's presigned
 *  original), for a PDF with `#page=<n>` so the browser's viewer opens on
 *  the cited page (pages are counted from 1, as the loader numbers them).
 *  Null when the source has nothing to open; the caller then only shows
 *  it in the list. */
export function citationTarget(source: Pick<Source, 'kind' | 'preview_url'> | undefined, page: number | null): string | null {
  const href = httpOnly(source?.preview_url)
  if (!href || source?.kind !== 'pdf' || page === null || !Number.isInteger(page) || page < 1) return href
  return `${href.split('#')[0]}#page=${page}`
}

function httpOnly(href: string | null | undefined): string | null {
  if (!href) return null
  try {
    const { protocol } = new URL(href)
    return protocol === 'https:' || protocol === 'http:' ? href : null
  } catch {
    return null
  }
}
