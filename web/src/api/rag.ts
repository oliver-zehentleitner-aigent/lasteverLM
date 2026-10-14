import { RAG_PREFIX } from '../config'
import { request } from './client'
import type { Answer, ChartCandidate, JudgeLevel, Chunk, Conversation, Message, Output, OutputKind, OutputOptions, OutputOptionsSpec, SharedNotebook, SharedOutput } from './types'

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
  /** every generated document of the notebook, before the notebook itself
   *  is deleted; without this call they stay in the library */
  deleteNotebookOutputs: (notebookId: string) => request<void>(`${nb(notebookId)}/outputs`, { method: 'DELETE' }),
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
  /** also without a notebook; 404 while it is in the trash */
  getOutput: (id: string) => request<Output>(out(id)),
  /** annotate only: every claim gets a judge note; 402 without credit, 409 without logged passages */
  judgeOutput: (id: string, level: Exclude<JudgeLevel, 'off'>) => request<Output>(`${out(id)}/judge`, { method: 'POST', json: { level } }),
  /** a cited answer, annotated the same way */
  judgeMessage: (id: string, level: Exclude<JudgeLevel, 'off'>) =>
    request<Message>(`${RAG_PREFIX}/messages/${encodeURIComponent(id)}/judge`, { method: 'POST', json: { level } }),
  renameOutput: (id: string, title: string) => request<Output>(out(id), { method: 'PATCH', json: { title } }),
  /** moves it to the trash: out of every notebook, its share link off */
  deleteOutput: (id: string) => request<void>(out(id), { method: 'DELETE' }),
  /** the user's generated documents, newest first; `trash` lists the trashed ones only */
  libraryOutputs: (trash = false, kind?: OutputKind) =>
    request<Output[]>(`${RAG_PREFIX}/library/outputs?trash=${trash}${kind ? `&kind=${encodeURIComponent(kind)}` : ''}`),
  /** back in the library, and in its notebook when that still exists */
  restoreOutput: (id: string) => request<void>(`${out(id)}/restore`, { method: 'POST' }),
  /** trashed ones only, 409 otherwise */
  purgeOutput: (id: string) => request<void>(`${out(id)}/purge`, { method: 'DELETE' }),

  share: (id: string) => request<{ share_token: string }>(`${out(id)}/share`, { method: 'POST' }),
  unshare: (id: string) => request<void>(`${out(id)}/share`, { method: 'DELETE' }),
  /** Charts the notebook's sources could carry: one billed model call (402
   *  without credit); an empty list says why in `reason`. */
  proposeCharts: (notebookId: string, body: { instructions?: string; max?: number }) =>
    request<{ candidates: ChartCandidate[]; reason: string | null }>(`${nb(notebookId)}/charts/propose`, { method: 'POST', json: body }),
  /** No auth: a shared notebook's public page; 404 for an unknown or revoked token. */
  getSharedNotebook: (token: string) =>
    request<SharedNotebook>(`${RAG_PREFIX}/shared/notebooks/${encodeURIComponent(token)}`, { anonymous: true }),
  /** No auth: the share page is reachable without login. */
  getShared: (token: string) =>
    request<SharedOutput>(`${RAG_PREFIX}/shared/${encodeURIComponent(token)}`, { anonymous: true }),
}
