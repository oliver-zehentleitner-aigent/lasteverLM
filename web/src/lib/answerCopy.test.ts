import { describe, expect, it } from 'vitest'
import type { Citation } from '../api/types'
import { answerForClipboard } from './answerCopy'

const cite = (n: number, page: number | null, quote: string): Citation => ({ n, source_id: 's', source_name: 'notes.pdf', source_kind: 'pdf', chunk_id: 'c', page, quote })

describe('answerForClipboard', () => {
  it('keeps the markers and lists the passages in order', () => {
    expect(answerForClipboard('Fog is dense [2] and wet [1].', [cite(2, 4, 'dense\n fog'), cite(1, null, 'wet')])).toBe(
      'Fog is dense [2] and wet [1].\n\nSources:\n[1] notes.pdf: "wet"\n[2] notes.pdf, p. 4: "dense fog"',
    )
  })

  it('is the answer alone without citations', () => {
    expect(answerForClipboard(' Plain. ', null)).toBe('Plain.')
  })
})
