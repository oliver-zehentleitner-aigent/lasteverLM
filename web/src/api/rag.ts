import { RAG_PREFIX } from '../config'
import { request } from './client'
import type { Answer, Chunk, Conversation, Message, Output, OutputKind, OutputOptions, OutputOptionsSpec, SharedOutput } from './types'

const nb = (id: string) => `${RAG_PREFIX}/notebooks/${encodeURIComponent(id)}`
const out = (id: string) => `${RAG_PREFIX}/outputs/${encodeURIComponent(id)}`
const conv = (id: string) => `${RAG_PREFIX}/conversations/${encodeURIComponent(id)}`

export const rag = {
  /** Every question belongs to a conversation; `scope.output_id` restricts
   *  retrieval to one generated document ("ask about this"), `source_ids`
   *  to the selected sources (left out when all are selected). */
  ask: (notebookId: string, conversationId: string, question: string, outputId?: string, sourceIds?: string[]) =>
    request<Answer>(`${nb(notebookId)}/ask`, {
      method: 'POST',
      json: {
        question,
        conversation_id: conversationId,
        ...(outputId ? { scope: { output_id: outputId } } : {}),
        ...(sourceIds ? { source_ids: sourceIds } : {}),
      },
    }),

  /** oldest first; the server names a new one "Chat N" */
  listConversations: (notebookId: string) => request<Conversation[]>(`${nb(notebookId)}/conversations`),
  createConversation: (notebookId: string) =>
    request<Conversation>(`${nb(notebookId)}/conversations`, { method: 'POST', json: {} }),
  /** a new title for a chat tab */
  renameConversation: (id: string, title: string) => request<Conversation>(conv(id), { method: 'PATCH', json: { title } }),
  /** removes the conversation and its messages */
  deleteConversation: (id: string) => request<void>(conv(id), { method: 'DELETE' }),
  listMessages: (conversationId: string) => request<Message[]>(`${conv(conversationId)}/messages`),

  /** owner only, 404 otherwise */
  getChunk: (chunkId: string) => request<Chunk>(`${RAG_PREFIX}/chunks/${encodeURIComponent(chunkId)}`),

  listOutputs: (notebookId: string) => request<Output[]>(`${nb(notebookId)}/outputs`),
  /** `options` only with the keys the kind takes; missing ones fall back to
   *  defaults. `sourceIds` limits the document to the selected sources
   *  (left out when all are selected). */
  createOutput: (notebookId: string, kind: OutputKind, options?: OutputOptions, sourceIds?: string[]) =>
    request<Output>(`${nb(notebookId)}/outputs`, {
      method: 'POST',
      json: {
        kind,
        ...(options && Object.keys(options).length > 0 ? { options } : {}),
        ...(sourceIds ? { source_ids: sourceIds } : {}),
      },
    }),

  /** A short fixed sentence pair spoken by a voice: synthesized once per
   *  voice, speed and language (about 1 cent, 402 without credit), then
   *  served from storage for everyone. */
  voiceSample: (voice: string, speed?: number, language?: string) =>
    request<{ url: string; cached: boolean }>(`${RAG_PREFIX}/outputs/voice-sample`, {
      method: 'POST',
      json: { voice, ...(speed !== undefined ? { speed } : {}), ...(language ? { language } : {}) },
    }),

  /** the choices per kind: languages, voices, speed */
  outputOptions: () => request<OutputOptionsSpec>(`${RAG_PREFIX}/outputs/options`),
  getOutput: (id: string) => request<Output>(out(id)),
  deleteOutput: (id: string) => request<void>(out(id), { method: 'DELETE' }),

  share: (id: string) => request<{ share_token: string }>(`${out(id)}/share`, { method: 'POST' }),
  unshare: (id: string) => request<void>(`${out(id)}/share`, { method: 'DELETE' }),
  /** No auth: the share page is reachable without login. */
  getShared: (token: string) =>
    request<SharedOutput>(`${RAG_PREFIX}/shared/${encodeURIComponent(token)}`, { anonymous: true }),
}
