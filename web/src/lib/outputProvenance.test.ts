import { marked } from 'marked'
import { describe, expect, it } from 'vitest'
import type { Passage } from '../api/types'
import { checkSummary, claimRefs, decorateReport, duration, exportName, markUnsupported, passageCitation, provenanceExport, supportBadge, unitBadges } from './outputProvenance'

const passage: Passage = {
  n: 2,
  chunk_id: 'c2',
  source_id: 's1',
  source_name: 'paper.pdf',
  source_kind: 'pdf',
  page: 4,
  chunk_index: 11,
  chunk_count: 40,
  similarity: 0.71,
  quote: 'Dead reckoning estimates a position from a known start.',
}

describe('passages and claims', () => {
  it('turns a passage into the chat citation, ids empty on the share page', () => {
    expect(passageCitation(passage)).toMatchObject({ n: 2, chunk_id: 'c2', source_id: 's1', page: 4, chunk_index: 11 })
    const { chunk_id: _c, source_id: _s, ...shared } = passage
    expect(passageCitation(shared)).toMatchObject({ chunk_id: '', source_id: '' })
  })

  it('keeps the refs that exist, each once', () => {
    expect(claimRefs({ refs: [2, 9, 2, 1] }, new Set([1, 2]))).toEqual([2, 1])
    expect(claimRefs({}, new Set([1]))).toEqual([])
  })

  it('badges only what is not backed', () => {
    expect(supportBadge('supported')).toBeNull()
    expect(supportBadge(undefined)).toBeNull()
    expect(supportBadge('unsupported')).toBe('unsupported')
    expect(supportBadge('unverified')).toBe('unverified')
  })
})

describe('checkSummary', () => {
  const check = { method: 'lexical-overlap-v1', threshold: 0.3, supported: 7, unsupported: 2, unverified: 0 }
  it('counts the supported claims of all', () => {
    expect(checkSummary(check)).toBe('7 of 9 claims supported')
    expect(checkSummary({ ...check, unverified: 1 })).toBe('7 of 10 claims supported · 1 not checkable')
  })
  it('says nothing without claims or a check', () => {
    expect(checkSummary({ ...check, supported: 0, unsupported: 0 })).toBeNull()
    expect(checkSummary(undefined)).toBeNull()
  })
})

describe('the report', () => {
  const md = '# Title\n\nFirst claim [1].\n\nSecond claim [2, 7].\n\n- a list item [1]\n'
  const units = [
    { text: 'First claim [1].', refs: [1], support: 'supported' as const },
    { text: 'Second claim [2, 7].', refs: [2], support: 'unsupported' as const },
  ]

  it('marks the paragraphs the check did not back, in order', () => {
    const out = markUnsupported(md, units)
    expect(out).toContain('First claim [1].\n')
    expect(out).toContain('Second claim [2, 7]. ⟦support:unsupported⟧')
    // a unit whose text is not in the markdown changes nothing
    expect(markUnsupported(md, [{ text: 'Not there', support: 'unsupported' }])).toBe(md)
  })

  it('turns known markers into buttons and sentinels into badges', () => {
    const html = decorateReport(marked.parse(markUnsupported(md, units), { async: false }) as string, new Set([1, 2]))
    expect(html).toContain('<button type="button" class="cite" data-n="1">1</button>')
    expect(html).toContain('<button type="button" class="cite" data-n="2">2</button>[7]')
    expect(html).toContain('class="badge support-unsupported"')
    expect(html).not.toContain('⟦')
  })

  it('leaves markers of unknown passages as text', () => {
    expect(decorateReport('<p>x [5]</p>', new Set([1]))).toBe('<p>x [5]</p>')
  })
})

describe('the log', () => {
  it('measures how long it took', () => {
    expect(duration({ started_at: '2026-10-14T10:00:00Z', finished_at: '2026-10-14T10:00:12Z' })).toBe('12 s')
    expect(duration({ started_at: '2026-10-14T10:00:00Z', finished_at: '2026-10-14T10:02:05Z' })).toBe('2 min 5 s')
    expect(duration({ started_at: 'x', finished_at: 'y' })).toBeNull()
  })

  it('exports the log with the document it belongs to', () => {
    const p = { version: 1 } as never
    expect(JSON.parse(provenanceExport({ id: 'o1', kind: 'report', title: 'T', created_at: 'now' }, p))).toEqual({
      output: { id: 'o1', kind: 'report', title: 'T', created_at: 'now' },
      provenance: { version: 1 },
    })
    expect(exportName('Dead reckoning: a Report!')).toBe('dead-reckoning-a-report-provenance.json')
    expect(exportName('???')).toBe('document-provenance.json')
  })
})

describe('unitBadges', () => {
  const answer = 'First paragraph [1].\n\nSecond one [2].\n\nThird [1, 2].'
  it('puts a badge after each paragraph the check did not back, in order', () => {
    const units = [
      { text: 'First paragraph [1].', support: 'supported' as const },
      { text: 'Second one [2].', support: 'unsupported' as const },
      { text: 'Third [1, 2].', support: 'unverified' as const },
    ]
    expect(unitBadges(answer, units)).toEqual([
      { end: answer.indexOf('Second one [2].') + 'Second one [2].'.length, badge: 'unsupported' },
      { end: answer.length, badge: 'unverified' },
    ])
  })
  it('has none without units or for a text it cannot find', () => {
    expect(unitBadges(answer, null)).toEqual([])
    expect(unitBadges(answer, [{ text: 'elsewhere', support: 'unsupported' }])).toEqual([])
  })
})
