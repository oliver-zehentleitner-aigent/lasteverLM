import { useEffect, useState, type ReactNode } from 'react'
import { rag } from '../api/rag'
import type { Citation, Conversation, Output } from '../api/types'
import type { Selection } from '../lib/sourceSelection'
import { useAsync } from '../hooks/useAsync'
import { useTabStrip } from '../hooks/useTabStrip'
import { activeAfterClose, renamedTitle } from '../lib/conversations'
import { t } from '../i18n'
import { ConversationView } from './ConversationView'

export interface ChatPaneProps {
  notebookId: string
  /** "ask about this": the document the next questions are scoped to */
  scope: Output | null
  /** sources a citation can still point to; others show as removed */
  presentSources: ReadonlySet<string> | null
  /** the sources selected in the list; a question goes to those only,
   *  unless it is about one document */
  sources: Selection
  onClearScope: () => void
  onCitationSelected: (c: Citation | null) => void
  /** "open in source" / "open document" in the provenance panel */
  onOpenSource: (c: Citation) => void
  /** controls at the right end of the tab bar (the chat height presets) */
  tools?: ReactNode
  /** a plan's step made a source or an output: open it as a viewer tab */
  onOpenTab?: (target: { type: 'source' | 'output'; id: string }) => void
  /** a plan's step made something: the notebook's lists reload */
  onWork?: () => void
}

/** A notebook without conversations gets its first one when the chat opens,
 *  so a question always has a conversation to go to. Concurrent calls for
 *  one notebook share the request, so a double mount (React's development
 *  mode) does not create two. */
const firstConversation = new Map<string, Promise<Conversation>>()

function createFirst(notebookId: string): Promise<Conversation> {
  let p = firstConversation.get(notebookId)
  if (!p) {
    p = rag.createConversation(notebookId).finally(() => firstConversation.delete(notebookId))
    firstConversation.set(notebookId, p)
  }
  return p
}

/** Right column, bottom: the chats of one notebook as tabs. "+" opens a new
 *  one, "×" deletes one with its messages after a confirmation; the last
 *  tab closed is replaced by a fresh one, so there is always a chat. */
export function ChatPane({ notebookId, scope, presentSources, sources, onClearScope, onCitationSelected, onOpenSource, tools, onOpenTab, onWork }: ChatPaneProps) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  // inline rename of a tab: which one, and the text being typed
  const [editing, setEditing] = useState<{ id: string; draft: string } | null>(null)
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => {
      const list = await rag.listConversations(notebookId)
      const shown = list.length > 0 ? list : [await createFirst(notebookId)]
      setConversations(shown)
      setActiveId(shown[shown.length - 1].id)
    })
  }, [notebookId, run])

  function select(id: string) {
    setActiveId(id)
    onCitationSelected(null)
  }

  async function add() {
    const created = await run(() => rag.createConversation(notebookId))
    if (created) {
      setConversations((prev) => [...prev, created])
      select(created.id)
    }
  }

  async function close(c: Conversation) {
    if (!confirm(t('chat.closeConfirm'))) return
    const next = await run(async () => {
      await rag.deleteConversation(c.id)
      const nextId = activeAfterClose(
        conversations.map((x) => x.id),
        c.id,
        activeId,
      )
      const rest = conversations.filter((x) => x.id !== c.id)
      if (nextId) return { list: rest, active: nextId }
      const fresh = await rag.createConversation(notebookId)
      return { list: [fresh], active: fresh.id }
    })
    if (next) {
      setConversations(next.list)
      if (next.active !== activeId) select(next.active)
    }
  }

  const active = conversations.find((c) => c.id === activeId) ?? null

  /** Saves the edited title (Enter or leaving the field); an empty or
   *  unchanged one keeps the old title. Shown at once, put back on error. */
  async function commitRename() {
    if (!editing) return
    const c = conversations.find((x) => x.id === editing.id)
    setEditing(null)
    const title = c ? renamedTitle(editing.draft, c.title) : null
    if (!c || !title) return
    setConversations((prev) => prev.map((x) => (x.id === c.id ? { ...x, title } : x)))
    const saved = await run(() => rag.renameConversation(c.id, title))
    setConversations((prev) => prev.map((x) => (x.id === c.id ? (saved ?? c) : x)))
  }
  const { ref: tabsRef, onWheel: onTabsWheel, onKeyDown: onTabsKey } = useTabStrip(
    conversations.map((c) => c.id),
    activeId,
    select,
  )

  return (
    <section className="pane chat">
      <div className="tabs chat-tabs">
        {/* only the tabs scroll; "+" and the tools stay in place */}
        <div className="tab-scroll" role="tablist" aria-label={t('chat.chats')} ref={tabsRef} onWheel={onTabsWheel} onKeyDown={onTabsKey}>
          {conversations.map((c) => (
            <span key={c.id} className={c.id === activeId ? 'tab active' : 'tab'}>
              {editing?.id === c.id ? (
                <input
                  className="tab-edit"
                  aria-label={t('chat.renameLabel')}
                  value={editing.draft}
                  size={Math.max(editing.draft.length, 4)}
                  maxLength={80}
                  autoFocus
                  onFocus={(e) => e.currentTarget.select()}
                  onChange={(e) => setEditing({ id: c.id, draft: e.target.value })}
                  onBlur={() => void commitRename()}
                  onKeyDown={(e) => {
                    // the field's keys move its caret, not the tab selection
                    e.stopPropagation()
                    if (e.key === 'Enter') void commitRename()
                    if (e.key === 'Escape') setEditing(null)
                  }}
                />
              ) : (
                <button
                  type="button"
                  role="tab"
                  data-tab-id={c.id}
                  tabIndex={c.id === activeId ? 0 : -1}
                  className="tab-label"
                  aria-selected={c.id === activeId}
                  title={t('chat.renameHint')}
                  onClick={() => select(c.id)}
                  onDoubleClick={() => setEditing({ id: c.id, draft: c.title })}
                  onKeyDown={(e) => {
                    if (e.key === 'F2') {
                      e.preventDefault()
                      setEditing({ id: c.id, draft: c.title })
                    }
                  }}
                >
                  {c.title}
                </button>
              )}
              <button type="button" className="icon" title={t('chat.close')} disabled={busy} onClick={() => void close(c)}>
                ×
              </button>
            </span>
          ))}
        </div>
        <button type="button" className="icon" title={t('chat.new')} disabled={busy} onClick={() => void add()}>
          +
        </button>
        {tools && <span className="tab-tools">{tools}</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {active && (
        <ConversationView
          key={active.id}
          notebookId={notebookId}
          conversationId={active.id}
          scope={scope}
          presentSources={presentSources}
          sources={sources}
          onClearScope={onClearScope}
          onCitationSelected={onCitationSelected}
          onOpenSource={onOpenSource}
          onOpenTab={onOpenTab}
          onWork={onWork}
        />
      )}
    </section>
  )
}
