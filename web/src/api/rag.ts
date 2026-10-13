import { RAG_PREFIX } from '../config'
import { request } from './client'
import type { Answer, Chunk, Conversation, Message, Output, OutputKind, SharedOutput } from './types'

const nb = (id: string) => `${RAG_PREFIX}/notebooks/${encodeURIComponent(id)}`
const out = (id: string) => `${RAG_PREFIX}/outputs/${encodeURIComponent(id)}`
const conv = (id: string) => `${RAG_PREFIX}/conversations/${encodeURIComponent(id)}`

export const rag = {
  /** Every question belongs to a conversation; `scope.output_id` restricts
   *  retrieval to one generated document ("ask about this"). */
  ask: (notebookId: string, conversationId: string, question: string, outputId?: string) =>
    request<Answer>(`${nb(notebookId)}/ask`, {
      method: 'POST',
      json: {
        question,
        conversation_id: conversationId,
        ...(outputId ? { scope: { output_id: outputId } } : {}),
      },
    }),

  /** oldest first; the server names a new one "Chat N" */
  listConversations: (notebookId: string) => request<Conversation[]>(`${nb(notebookId)}/conversations`),
  createConversation: (notebookId: string) =>
    request<Conversation>(`${nb(notebookId)}/conversations`, { method: 'POST', json: {} }),
  /** removes the conversation and its messages */
  deleteConversation: (id: string) => request<void>(conv(id), { method: 'DELETE' }),
  listMessages: (conversationId: string) => request<Message[]>(`${conv(conversationId)}/messages`),

  /** owner only, 404 otherwise */
  getChunk: (chunkId: string) => request<Chunk>(`${RAG_PREFIX}/chunks/${encodeURIComponent(chunkId)}`),

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
