import { describe, expect, it } from 'vitest'
import type { Source } from '../api/types'
import { SOURCE_FORMS, createBlocker, tileNote, uploadedSources } from './outputs'

describe('tileNote', () => {
  it('shows the description of an available form', () => {
    expect(tileNote({ description: 'A structured write-up.', available: true })).toBe('A structured write-up.')
  })

  it('shows "Soon." for a form that is not available yet', () => {
    expect(tileNote({ description: 'A spoken overview.', available: false })).toBe('Soon.')
  })
})

describe('forms', () => {
  it('offers every source kind the ingest service accepts', () => {
    expect(SOURCE_FORMS.filter((f) => f.available).map((f) => f.kind)).toEqual(['pdf', 'text', 'url', 'image', 'audio'])
  })
})

describe('uploadedSources', () => {
  const src = (id: string, kind: Source['kind']): Source => ({
    id,
    notebook_id: 'n',
    name: id,
    kind,
    status: 'ready',
    error: null,
    created_at: '2026-10-13T00:00:00Z',
  })

  it('drops generated documents and keeps every upload kind', () => {
    const list = [src('a', 'pdf'), src('b', 'generated'), src('c', 'text'), src('d', 'url'), src('e', 'image')]
    expect(uploadedSources(list).map((s) => s.id)).toEqual(['a', 'c', 'd', 'e'])
  })
})

describe('createBlocker', () => {
  it('asks for a ready source first, then for a format', () => {
    expect(createBlocker(null, false)).toBe('Add a source and wait until it is ready.')
    expect(createBlocker('report', false)).toBe('Add a source and wait until it is ready.')
    expect(createBlocker(null, true)).toBe('Pick a format above.')
  })

  it('lets a job start with a format and a ready source', () => {
    expect(createBlocker('quiz', true)).toBeNull()
  })
})
