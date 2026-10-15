import { t, tn } from '../i18n'

/** A document's or an answer's cited passages grouped by source, so a file
 *  cited three times is one row: "handbook.pdf · p. 27 [1] [2] · p. 31 [5]".
 *  Pure, so it is tested. */

interface Cited {
  n: number
  /** absent on the share page, where the name tells the sources apart; null for a copied starter passage */
  source_id?: string | null
  source_name: string
  page: number | null
}

export interface SourceGroup<T extends Cited> {
  key: string
  name: string
  /** the source's first passage, for what all its passages share (kind, removed) */
  first: T
  /** its passages by locator, in order of the page (no page first), each in number order */
  locators: { page: number | null; passages: T[] }[]
}

export function groupBySource<T extends Cited>(passages: readonly T[]): SourceGroup<T>[] {
  const groups = new Map<string, T[]>()
  for (const p of [...passages].sort((a, b) => a.n - b.n)) {
    const key = p.source_id || `name:${p.source_name}`
    groups.set(key, [...(groups.get(key) ?? []), p])
  }
  // sources in the order they are first cited
  return [...groups.entries()].map(([key, list]) => {
    const pages = new Map<number | null, T[]>()
    for (const p of list) pages.set(p.page, [...(pages.get(p.page) ?? []), p])
    const locators = [...pages.entries()]
      .sort(([a], [b]) => (a ?? -1) - (b ?? -1))
      .map(([page, ps]) => ({ page, passages: ps }))
    return { key, name: list[0].source_name, first: list[0], locators }
  })
}

/** "Sources (4) · 8 passages": how many sources, and how many passages of them are cited. */
export function sourcesHead(sources: number, passages: number): string {
  return `${t('outProv.sources', { n: sources })} · ${tn('outProv.passages', passages)}`
}
