import { INGEST_PREFIX } from '../config'
import { request, requestWithStatus } from './client'
import type { LibraryEntry, Notebook, Source } from './types'

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

  deleteNotebook: (id: string) =>
    request<void>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  listSources: (notebookId: string) =>
    request<Source[]>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(notebookId)}/sources`),

  /** The same bytes or URL again link the existing library entry: 202 for a
   *  new link, 200 when it was already in this notebook (`existing`). */
  uploadFile: (notebookId: string, file: File) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return addSource(notebookId, { form })
  },

  addUrl: (notebookId: string, url: string) => addSource(notebookId, { json: { url } }),

  /** add an existing library entry; 200 with the existing link when it is already in */
  addFromLibrary: (notebookId: string, libraryId: string) => addSource(notebookId, { json: { library_id: libraryId } }),

  /** newest first, generated documents never listed */
  listLibrary: () => request<LibraryEntry[]>(`${INGEST_PREFIX}/library`),
  /** removes the entry from every notebook, with its chunks and stored object */
  deleteLibraryEntry: (id: string) =>
    request<void>(`${INGEST_PREFIX}/library/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  /** detaches: the source leaves this notebook and stays in the library */
  deleteSource: (id: string) =>
    request<void>(`${INGEST_PREFIX}/sources/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
