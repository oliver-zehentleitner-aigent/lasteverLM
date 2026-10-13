/** Which of a notebook's sources the chat and new documents use. Every
 *  source is on by default; the browser remembers the ones turned off,
 *  per notebook, so a source added later starts selected. */

const key = (notebookId: string) => `lasteverlm.sources-off.${notebookId}`

export function readExcluded(storage: Pick<Storage, 'getItem'> | undefined, notebookId: string): Set<string> {
  try {
    const raw = storage?.getItem(key(notebookId))
    const list: unknown = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(list) ? list.filter((x): x is string => typeof x === 'string') : [])
  } catch {
    return new Set()
  }
}

export function writeExcluded(storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined, notebookId: string, excluded: Set<string>): void {
  try {
    if (excluded.size === 0) storage?.removeItem(key(notebookId))
    else storage?.setItem(key(notebookId), JSON.stringify([...excluded]))
  } catch {
    // not remembered in this browser; the selection still applies until reload
  }
}

export interface Selection {
  selected: number
  total: number
  /** the ids to send, or undefined when every source is selected (the
   *  request then names none and the service uses all of them) */
  sourceIds: string[] | undefined
}

/** The selection over the sources the notebook has now; ids of sources
 *  that are gone are ignored. */
export function selection(sourceIds: string[], excluded: Set<string>): Selection {
  const on = sourceIds.filter((id) => !excluded.has(id))
  return { selected: on.length, total: sourceIds.length, sourceIds: on.length === sourceIds.length ? undefined : on }
}

/** Turns one source on or off. */
export function toggled(excluded: Set<string>, id: string): Set<string> {
  const next = new Set(excluded)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return next
}

export interface MadeFrom {
  n: number
  /** the names of those still in the notebook */
  names: string[]
  /** how many have been removed since */
  removed: number
}

/** What a document was made from, from `Output.options.sources` (absent
 *  when all sources were used); names come from the current list, since
 *  a removed source keeps its id there. */
export function madeFrom(ids: string[] | undefined, sources: { id: string; name: string }[]): MadeFrom | null {
  if (!ids || ids.length === 0) return null
  const byId = new Map(sources.map((s) => [s.id, s.name]))
  const names = ids.flatMap((id) => (byId.has(id) ? [byId.get(id)!] : []))
  return { n: ids.length, names, removed: ids.length - names.length }
}
