import type { SourceKind } from '../api/types'

/** One tab in the viewer: an output or a source the user opened (from its
 *  list, or from a citation). The lists stay the index; the tabs hold only
 *  what was opened, in the order it was opened. */
export interface ViewerTab {
  type: 'output' | 'source'
  id: string
  /** where a citation pointed into a source: its page (a PDF's Original)
   *  and chunk (As read); null otherwise */
  page?: number | null
  chunkId?: string | null
  /** the cited chunk's 0-based position, to load the page of chunks it is on */
  chunkIndex?: number | null
  /** bumps on every open, so opening the same citation again scrolls and flashes */
  nonce?: number
}

export type SourceViewMode = 'original' | 'read'

/** A tab's key in the strip: outputs and sources share one selection. */
export const tabKey = (tab: Pick<ViewerTab, 'type' | 'id'>) => `${tab.type}:${tab.id}`

/** The tabs after opening one: a new one goes at the end (the order of
 *  opening); one already open keeps its place and takes the new target. */
export function openTab(tabs: readonly ViewerTab[], next: ViewerTab): ViewerTab[] {
  const at = tabs.findIndex((x) => x.type === next.type && x.id === next.id)
  const tab: ViewerTab = { ...next, nonce: (at >= 0 ? (tabs[at].nonce ?? 0) : 0) + 1 }
  return at >= 0 ? tabs.map((x, i) => (i === at ? tab : x)) : [...tabs, tab]
}

/** The tab to show after closing one: its right neighbour, else its left. */
export function afterClose(keys: readonly string[], closing: string): string | null {
  const at = keys.indexOf(closing)
  if (at < 0) return null
  return keys[at + 1] ?? keys[at - 1] ?? null
}

/** "As read" first where the extracted text is the source (text, a web
 *  page), "Original" where it renders something else (image, audio, PDF). */
export function defaultView(kind: SourceKind): SourceViewMode {
  return kind === 'text' || kind === 'url' ? 'read' : 'original'
}

/** The open tabs and the active one per notebook, for this browser
 *  session: a reload keeps them, a new session starts empty. Targets
 *  (page, chunk) are not kept; a restored tab opens at its top. */
export interface StoredTabs {
  tabs: ViewerTab[]
  active: string | null
}

const key = (notebookId: string) => `lasteverlm.tabs.${notebookId}`

export function readTabs(storage: Pick<Storage, 'getItem'> | undefined, notebookId: string): StoredTabs {
  try {
    const raw: unknown = JSON.parse(storage?.getItem(key(notebookId)) ?? 'null')
    if (!raw || typeof raw !== 'object') return { tabs: [], active: null }
    const r = raw as { tabs?: unknown; active?: unknown }
    const tabs = Array.isArray(r.tabs)
      ? r.tabs.filter((x): x is ViewerTab => !!x && typeof x === 'object' && (x.type === 'output' || x.type === 'source') && typeof x.id === 'string').map((x) => ({ type: x.type, id: x.id }))
      : []
    const active = typeof r.active === 'string' && tabs.some((x) => tabKey(x) === r.active) ? r.active : null
    return { tabs, active }
  } catch {
    return { tabs: [], active: null }
  }
}

export function writeTabs(storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined, notebookId: string, s: StoredTabs): void {
  try {
    if (s.tabs.length === 0) storage?.removeItem(key(notebookId))
    else storage?.setItem(key(notebookId), JSON.stringify({ tabs: s.tabs.map((x) => ({ type: x.type, id: x.id })), active: s.active }))
  } catch {
    // no session storage (private mode, blocked): the tabs last until the page goes
  }
}

/** Drops the tabs of one type whose output or source is no longer listed;
 *  the same array when nothing goes, so a caller's state does not change. */
export function dropMissing(tabs: ViewerTab[], type: ViewerTab['type'], ids: ReadonlySet<string>): ViewerTab[] {
  const kept = tabs.filter((x) => x.type !== type || ids.has(x.id))
  return kept.length === tabs.length ? tabs : kept
}

/** The session's storage, or undefined where the browser refuses it. */
export function sessionStore(): Storage | undefined {
  try {
    return window.sessionStorage
  } catch {
    return undefined
  }
}

/** Chunks per page in a source's As read view. */
export const CHUNK_PAGE = 50

/** The offset of the page a chunk is on, so a citation opens its page. */
export function chunkPageOffset(chunkIndex: number | null | undefined, size = CHUNK_PAGE): number {
  return chunkIndex != null && chunkIndex > 0 ? Math.floor(chunkIndex / size) * size : 0
}
