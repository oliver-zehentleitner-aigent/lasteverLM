import { describe, expect, it } from 'vitest'
import type { LibraryEntry } from '../api/types'
import { bulkDeleteConfirmText, deleteConfirmText, filterLibrary, notebookTitleFrom, notInNotebook, purgeIn, shortUrl } from './library'

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
  it('takes the first name without its extension', () => {
    expect(notebookTitleFrom([{ name: 'linux_-_vi.pdf', kind: 'pdf' }, { name: 'b.txt', kind: 'text' }])).toBe('linux_-_vi')
  })

  it('keeps a web page title whole and is empty for no entries', () => {
    expect(notebookTitleFrom([{ name: 'Danube - Wikipedia', kind: 'url' }])).toBe('Danube - Wikipedia')
    expect(notebookTitleFrom([])).toBe('')
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
