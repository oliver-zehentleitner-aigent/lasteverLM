import { INGEST_PREFIX } from '../config'
import { request, requestWithStatus } from './client'
import { isPdf, type CaptureMode } from '../lib/capture'
import type { LibraryEntry, Notebook, Source, SourceChunks, TrashEntry } from './types'

export interface Added {
  source: Source
  /** it was in this notebook already; nothing was stored or processed */
  existing: boolean
}

function addSource(notebookId: string, body: { form?: FormData; json?: unknown }): Promise<Added> {
  return requestWithStatus<Source>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(notebookId)}/sources`, {
    method: 'POST',
    ...body,
  }).then((r) => ({ source: r.body, existing: r.status === 200 }))
}

export const ingest = {
  listNotebooks: () => request<Notebook[]>(`${INGEST_PREFIX}/notebooks`),
  /** a fresh copy of the current starter notebook, free; 409 "starter_exists"
   *  while the user has one (then `force`), 429 "starter_copy_too_soon", 404 "no_starter" */
  copyStarter: (force: boolean) => request<Notebook>(`${INGEST_PREFIX}/starter/copy${force ? '?force=true' : ''}`, { method: 'POST' }),

  createNotebook: (title: string) =>
    request<Notebook>(`${INGEST_PREFIX}/notebooks`, { method: 'POST', json: { title } }),

  /** 1–200 characters after trimming, else 400 */
  renameNotebook: (id: string, title: string) =>
    request<Notebook>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(id)}`, { method: 'PATCH', json: { title } }),

  /** the same token on every call until it is revoked */
  shareNotebook: (id: string) =>
    request<{ share_token: string }>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(id)}/share`, { method: 'POST' }),
  unshareNotebook: (id: string) =>
    request<void>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(id)}/share`, { method: 'DELETE' }),

  deleteNotebook: (id: string) =>
    request<void>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  listSources: (notebookId: string) =>
    request<Source[]>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(notebookId)}/sources`),

  /** The same bytes or URL again link the existing library entry: 202 for a
   *  new link, 200 when it was already in this notebook (`existing`). */
  uploadFile: (notebookId: string, file: File, capture?: CaptureMode) => {
    const form = new FormData()
    form.append('file', file, file.name)
    // only PDFs take a capture mode; the same bytes in another mode are another entry
    if (capture && isPdf(file)) form.append('capture', capture)
    return addSource(notebookId, { form })
  },

  addUrl: (notebookId: string, url: string) => addSource(notebookId, { json: { url } }),

  /** add an existing library entry; 200 with the existing link when it is already in */
  addFromLibrary: (notebookId: string, libraryId: string) => addSource(notebookId, { json: { library_id: libraryId } }),

  /** newest first; `all` lists uploads and generated documents together */
  listLibrary: (kind: 'all' | 'uploads' = 'all') => request<LibraryEntry[]>(`${INGEST_PREFIX}/library${kind === 'all' ? '?kind=all' : ''}`),
  /** links several library entries at once; `added` and `already` are library ids in request order */
  addManyFromLibrary: (notebookId: string, libraryIds: string[]) =>
    request<{ added: string[]; already: string[] }>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(notebookId)}/sources/bulk`, {
      method: 'POST',
      json: { library_ids: libraryIds },
    }),
  /** moves the entry to the trash: gone from every notebook, kept until purged */
  deleteLibraryEntry: (id: string) =>
    request<void>(`${INGEST_PREFIX}/library/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  /** most recently deleted first */
  listTrash: () => request<TrashEntry[]>(`${INGEST_PREFIX}/library/trash`),
  /** back in the library, in no notebook */
  restoreFromTrash: (id: string) =>
    request<void>(`${INGEST_PREFIX}/library/${encodeURIComponent(id)}/restore`, { method: 'POST' }),
  /** gone for good, chunks and stored object included */
  purgeFromTrash: (id: string) =>
    request<void>(`${INGEST_PREFIX}/library/${encodeURIComponent(id)}/purge`, { method: 'DELETE' }),

  /** reads unread sources now (idempotent: reading, read or failed come back unchanged); 404 for another user's */
  processSources: (libraryIds: string[]) =>
    request<{ queued: string[]; unchanged: string[] }>(`${INGEST_PREFIX}/sources/process`, { method: 'POST', json: { library_ids: libraryIds } }),
  /** the price of reading them, per source */
  readEstimate: (libraryIds: string[]) =>
    request<{ items: { library_id: string; charge_cents_min: number; charge_cents_max: number; basis?: string | null }[] }>(`${INGEST_PREFIX}/sources/estimate`, { method: 'POST', json: { library_ids: libraryIds } }),
  /** fetches a web page again; the version goes up when it changed */
  refetchSource: (id: string) =>
    request<{ library_id: string; version: number; fetched_at: string }>(`${INGEST_PREFIX}/sources/${encodeURIComponent(id)}/refetch`, { method: 'POST' }),

  /** a text or Markdown source's stored file as text (capped by the service), readable before it is read */
  sourceText: (id: string) => request<string>(`${INGEST_PREFIX}/sources/${encodeURIComponent(id)}/text`, { text: true }),

  /** the extracted text, a page of chunks (limit 1–200) in order */
  sourceChunks: (id: string, offset: number, limit: number) =>
    request<SourceChunks>(`${INGEST_PREFIX}/sources/${encodeURIComponent(id)}/chunks?offset=${offset}&limit=${limit}`),

  /** detaches: the source leaves this notebook and stays in the library */
  deleteSource: (id: string) =>
    request<void>(`${INGEST_PREFIX}/sources/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
