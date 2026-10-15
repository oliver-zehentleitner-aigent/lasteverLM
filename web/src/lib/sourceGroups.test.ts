import { describe, expect, it } from 'vitest'
import { groupBySource, sourcesHead } from './sourceGroups'

const p = (n: number, source_id: string, source_name: string, page: number | null) => ({ n, source_id, source_name, page })

describe('groupBySource', () => {
  it('makes one row per source, in the order first cited, with its passages by page', () => {
    const groups = groupBySource([p(4, 's2', 'faq.txt', null), p(2, 's1', 'handbook.pdf', 27), p(1, 's1', 'handbook.pdf', 27), p(7, 's2', 'faq.txt', null), p(5, 's1', 'handbook.pdf', 31), p(3, 's3', 'notes.md', null)])
    expect(groups.map((g) => [g.name, g.locators.map((l) => [l.page, l.passages.map((x) => x.n)])])).toEqual([
      ['handbook.pdf', [[27, [1, 2]], [31, [5]]]],
      ['notes.md', [[null, [3]]]],
      ['faq.txt', [[null, [4, 7]]]],
    ])
  })

  it('tells sources apart by name where there are no ids (the share page)', () => {
    const shared = [{ n: 1, source_name: 'a.pdf', page: 1 }, { n: 2, source_name: 'a.pdf', page: 2 }, { n: 3, source_name: 'b.pdf', page: null }]
    expect(groupBySource(shared).map((g) => g.name)).toEqual(['a.pdf', 'b.pdf'])
  })

  it('keeps two sources of the same name apart by id', () => {
    expect(groupBySource([p(1, 's1', 'notes.md', null), p(2, 's2', 'notes.md', null)])).toHaveLength(2)
  })

  it('puts passages without a page before the pages', () => {
    expect(groupBySource([p(1, 's1', 'x.pdf', 3), p(2, 's1', 'x.pdf', null)])[0].locators.map((l) => l.page)).toEqual([null, 3])
  })
})

describe('sourcesHead', () => {
  it('counts sources and passages', () => {
    expect(sourcesHead(4, 8)).toBe('Sources (4) · 8 passages')
    expect(sourcesHead(1, 1)).toBe('Sources (1) · 1 passage')
  })
})
