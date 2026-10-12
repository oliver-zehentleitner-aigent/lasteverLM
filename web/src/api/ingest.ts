import { INGEST_PREFIX } from '../config'
import { request } from './client'
import type { Notebook, Source } from './types'

export const ingest = {
  listNotebooks: () => request<Notebook[]>(`${INGEST_PREFIX}/notebooks`),

  createNotebook: (title: string) =>
    request<Notebook>(`${INGEST_PREFIX}/notebooks`, { method: 'POST', json: { title } }),

  deleteNotebook: (id: string) =>
    request<void>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  listSources: (notebookId: string) =>
    request<Source[]>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(notebookId)}/sources`),

  uploadFile: (notebookId: string, file: File) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return request<Source>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(notebookId)}/sources`, {
      method: 'POST',
      form,
    })
  },

  addUrl: (notebookId: string, url: string) =>
    request<Source>(`${INGEST_PREFIX}/notebooks/${encodeURIComponent(notebookId)}/sources`, {
      method: 'POST',
      json: { url },
    }),

  deleteSource: (id: string) =>
    request<void>(`${INGEST_PREFIX}/sources/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
