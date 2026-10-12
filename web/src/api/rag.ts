import { RAG_PREFIX } from '../config'
import { request } from './client'
import type { Answer, Message, Output, OutputKind, SharedOutput } from './types'

const nb = (id: string) => `${RAG_PREFIX}/notebooks/${encodeURIComponent(id)}`
const out = (id: string) => `${RAG_PREFIX}/outputs/${encodeURIComponent(id)}`

export const rag = {
  /** `scope.output_id` restricts retrieval to one generated document ("ask about this"). */
  ask: (notebookId: string, question: string, outputId?: string) =>
    request<Answer>(`${nb(notebookId)}/ask`, {
      method: 'POST',
      json: outputId ? { question, scope: { output_id: outputId } } : { question },
    }),

  listMessages: (notebookId: string) => request<Message[]>(`${nb(notebookId)}/messages`),

  listOutputs: (notebookId: string) => request<Output[]>(`${nb(notebookId)}/outputs`),
  createOutput: (notebookId: string, kind: OutputKind) =>
    request<Output>(`${nb(notebookId)}/outputs`, { method: 'POST', json: { kind } }),
  getOutput: (id: string) => request<Output>(out(id)),
  deleteOutput: (id: string) => request<void>(out(id), { method: 'DELETE' }),

  share: (id: string) => request<{ share_token: string }>(`${out(id)}/share`, { method: 'POST' }),
  unshare: (id: string) => request<void>(`${out(id)}/share`, { method: 'DELETE' }),
  /** No auth: the share page is reachable without login. */
  getShared: (token: string) =>
    request<SharedOutput>(`${RAG_PREFIX}/shared/${encodeURIComponent(token)}`, { anonymous: true }),
}
