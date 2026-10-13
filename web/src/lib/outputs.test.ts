import { describe, expect, it } from 'vitest'
import { SOURCE_FORMS, tileNote } from './outputs'

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
    expect(SOURCE_FORMS.filter((f) => f.available).map((f) => f.kind)).toEqual(['pdf', 'text', 'url', 'image'])
  })
})
