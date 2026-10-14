import { INGEST_PREFIX } from '../config'
import { request, requestWithStatus } from './client'
import { isPdf, type CaptureMode } from '../lib/capture'
import type { LibraryEntry, Notebook, Source, TrashEntry } from './types'

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

  /** detaches: the source leaves this notebook and stays in the library */
  deleteSource: (id: string) =>
    request<void>(`${INGEST_PREFIX}/sources/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
