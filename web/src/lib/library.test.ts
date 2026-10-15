import { describe, expect, it } from 'vitest'
import type { LibraryEntry } from '../api/types'
import { addPlan, addedSummary, bulkDeleteConfirmText, deleteConfirmText, filterLibrary, notebookTitleFrom, notInNotebook, pageTitleFrom, purgeIn, shortUrl, rangeIds } from './library'

const entry = (id: string, kind: LibraryEntry['kind'], name: string, notebooks: LibraryEntry['notebooks'] = [], url: string | null = null): LibraryEntry => ({
  id,
  name,
  kind,
  status: 'ready',
  error: null,
  size_bytes: url ? null : 100,
  url,
  created_at: '2026-10-13T00:00:00Z',
  notebooks,
})

const list = [
  entry('a', 'pdf', 'Thesis.pdf', [{ id: 'n1', title: 'Thesis', source_id: 's1' }]),
  entry('b', 'url', 'https://example.org/Danube', [], 'https://example.org/Danube'),
  entry('c', 'text', 'notes.txt', [
    { id: 'n1', title: 'Thesis', source_id: 's2' },
    { id: 'n2', title: 'Rivers', source_id: 's3' },
  ]),
]

describe('filterLibrary', () => {
  it('filters by kind and by a part of the name, case-insensitive', () => {
    expect(filterLibrary(list, { kind: 'all', query: '' }).map((e) => e.id)).toEqual(['a', 'b', 'c'])
    expect(filterLibrary(list, { kind: 'pdf', query: '' }).map((e) => e.id)).toEqual(['a'])
    expect(filterLibrary(list, { kind: 'all', query: 'NOTES' }).map((e) => e.id)).toEqual(['c'])
    expect(filterLibrary(list, { kind: 'all', query: 'danube' }).map((e) => e.id)).toEqual(['b'])
  })
})

describe('notInNotebook', () => {
  it('offers only entries the notebook does not have yet', () => {
    expect(notInNotebook(list, 'n1').map((e) => e.id)).toEqual(['b'])
    expect(notInNotebook(list, 'n2').map((e) => e.id)).toEqual(['a', 'b'])
  })
})

describe('deleteConfirmText', () => {
  it('names every notebook the entry disappears from', () => {
    expect(deleteConfirmText(list[2])).toBe(
      'Move "notes.txt" to the trash? It disappears from these 2 notebooks: "Thesis", "Rivers". It stays restorable in the trash until it is purged; citations to it show as removed meanwhile.',
    )
    expect(deleteConfirmText(list[0])).toContain('It disappears from this notebook: "Thesis".')
    expect(deleteConfirmText(list[1])).toContain('It is not in any notebook.')
  })
})

describe('bulkDeleteConfirmText', () => {
  it('counts the entries and names each notebook once', () => {
    const text = bulkDeleteConfirmText([list[0], list[2]])
    expect(text).toContain('Move 2 entries to the trash?')
    expect(text).toContain('They disappear from these 2 notebooks: "Thesis", "Rivers".')
  })

  it('says when none of them is in a notebook', () => {
    expect(bulkDeleteConfirmText([list[1]])).toContain('None of them is in a notebook.')
  })
})

describe('notebookTitleFrom', () => {
  const page = (url: string, name = url) => ({ name, kind: 'url' as const, url })

  it('takes the first file name without its extension', () => {
    expect(notebookTitleFrom([{ name: 'linux_-_vi.pdf', kind: 'pdf', url: null }, { name: 'b.txt', kind: 'text', url: null }])).toBe('linux_-_vi')
  })

  it('prefers a file to a web page among several', () => {
    expect(notebookTitleFrom([page('https://en.wikipedia.org/wiki/Danube'), { name: 'notes.txt', kind: 'text', url: null }])).toBe('notes')
  })

  it('never offers a raw address', () => {
    expect(notebookTitleFrom([page('https://en.wikipedia.org/wiki/Dead_reckoning')])).toBe('en.wikipedia.org · Dead reckoning')
    expect(notebookTitleFrom([page('https://en.wikipedia.org/wiki/Dead_reckoning'), page('https://example.com/b')])).toBe('en.wikipedia.org · Dead reckoning')
  })

  it("keeps a web page's stored title whole", () => {
    expect(notebookTitleFrom([page('https://en.wikipedia.org/wiki/Danube', 'Danube - Wikipedia')])).toBe('Danube - Wikipedia')
  })

  it('is empty for no entries', () => {
    expect(notebookTitleFrom([])).toBe('')
  })
})

describe('pageTitleFrom', () => {
  it('names host and last path segment', () => {
    expect(pageTitleFrom('https://www.example.com/blog/my-first_post/')).toBe('example.com · my first post')
    expect(pageTitleFrom('https://example.com/docs/guide.html?x=1#top')).toBe('example.com · guide')
    expect(pageTitleFrom('https://de.wikipedia.org/wiki/K%C3%B6ln')).toBe('de.wikipedia.org · Köln')
  })

  it('is the host alone without a path', () => {
    expect(pageTitleFrom('https://example.com/')).toBe('example.com')
    expect(pageTitleFrom('https://example.com/---/')).toBe('example.com')
  })

  it('survives a malformed escape and a non-address', () => {
    expect(pageTitleFrom('https://example.com/a%E0%A4%A')).toBe('example.com · a%E0%A4%A')
    expect(pageTitleFrom('not a url')).toBe('not a url')
  })
})

describe('purgeIn', () => {
  const now = new Date('2026-10-13T12:00:00Z')

  it('counts whole days until the purge', () => {
    expect(purgeIn('2026-10-27T12:00:00Z', now)).toBe('purged in 14 days')
    expect(purgeIn('2026-10-14T06:00:00Z', now)).toBe('purged in 1 day')
    expect(purgeIn('2026-10-13T11:00:00Z', now)).toBe('purged today')
  })
})

describe('shortUrl', () => {
  it('keeps host and path', () => {
    expect(shortUrl('https://en.wikipedia.org/wiki/Dead_reckoning')).toBe('en.wikipedia.org/wiki/Dead_reckoning')
    expect(shortUrl('http://www.example.org/')).toBe('example.org')
    expect(shortUrl('https://example.org/a?b=1')).toBe('example.org/a?b=1')
    expect(shortUrl('not a url')).toBe('not a url')
  })
})


describe('the one table', () => {
  const nb = (id: string) => ({ id, title: id, source_id: 's' })
  const entry = (id: string, kind: LibraryEntry['kind'], notebooks: string[] = []) =>
    ({ id, name: id, kind, status: 'ready', error: null, size_bytes: null, url: null, created_at: '2026-10-14T00:00:00Z', notebooks: notebooks.map(nb) }) as LibraryEntry
  const all = [entry('a.pdf', 'pdf', ['n1']), entry('Report on X', 'generated', ['n1', 'n2']), entry('b.txt', 'text')]
  const docKind = (e: LibraryEntry) => (e.kind === 'generated' ? ('report' as const) : null)

  it('narrows by view, a document kind and a notebook', () => {
    const f = { kind: 'all' as const, query: '' }
    expect(filterLibrary(all, { ...f, view: 'outputs' }).map((e) => e.id)).toEqual(['Report on X'])
    expect(filterLibrary(all, { ...f, view: 'sources' }).map((e) => e.id)).toEqual(['a.pdf', 'b.txt'])
    expect(filterLibrary(all, { ...f, kind: 'report' }, docKind).map((e) => e.id)).toEqual(['Report on X'])
    expect(filterLibrary(all, { ...f, notebook: 'n2' }).map((e) => e.id)).toEqual(['Report on X'])
    expect(filterLibrary(all, { ...f, notebook: 'none' }).map((e) => e.id)).toEqual(['b.txt'])
  })

  it('adds only what is not in the notebook yet, and only ready documents', () => {
    expect(addPlan(all, 'n1')).toEqual({ already: 2, toAdd: ['b.txt'], skipped: 0 })
    expect(addPlan(all, 'n3', (e) => e.kind !== 'generated')).toEqual({ already: 0, toAdd: ['a.pdf', 'b.txt'], skipped: 1 })
    expect(addPlan(all.slice(0, 2), 'n1').toAdd).toEqual([])
  })

  it('says what happened', () => {
    expect(addedSummary(2, 1, 'test1')).toBe('2 added, 1 was already in test1')
    expect(addedSummary(1, 0, 'test1')).toBe('1 added')
  })
})

describe('rangeIds', () => {
  const ids = ['a', 'b', 'c', 'd', 'e']
  it('takes every row between the last clicked and this one, either way', () => {
    expect(rangeIds(ids, 'b', 'd')).toEqual(['b', 'c', 'd'])
    expect(rangeIds(ids, 'd', 'b')).toEqual(['b', 'c', 'd'])
    expect(rangeIds(ids, 'c', 'c')).toEqual(['c'])
  })
  it('is just this row without a last one that is still shown', () => {
    expect(rangeIds(ids, null, 'c')).toEqual(['c'])
    expect(rangeIds(ids, 'gone', 'c')).toEqual(['c'])
    expect(rangeIds(ids, 'a', 'gone')).toEqual([])
  })
})
