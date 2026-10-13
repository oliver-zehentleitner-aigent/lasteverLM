import type { LibraryEntry } from '../api/types'

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
      ? 'It is not in any notebook.'
      : `It disappears from ${e.notebooks.length === 1 ? 'this notebook' : `these ${e.notebooks.length} notebooks`}: ${e.notebooks
          .map((n) => `"${n.title}"`)
          .join(', ')}.`
  return `Delete "${e.name}" from your library? ${where} Citations to it show as removed.`
}
