import { describe, expect, it } from 'vitest'
import type { LibraryEntry } from '../api/types'
import { deleteConfirmText, filterLibrary, notInNotebook } from './library'

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
      'Delete "notes.txt" from your library? It disappears from these 2 notebooks: "Thesis", "Rivers". Citations to it show as removed.',
    )
    expect(deleteConfirmText(list[0])).toContain('It disappears from this notebook: "Thesis".')
    expect(deleteConfirmText(list[1])).toContain('It is not in any notebook.')
  })
})
