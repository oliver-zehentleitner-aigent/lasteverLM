import { describe, expect, it } from 'vitest'
import type { ChartSpec } from '../api/types'
import { chartCsv, chartFileName, chartRows, pointAt, pointPassage, proposalKey, supportCount, supportLine } from './chartOutput'

const chart: ChartSpec = {
  title: 'Revenue by year',
  chart_type: 'bar',
  x_label: 'Year',
  y_label: 'EUR m',
  note: '',
  series: [
    {
      name: 'Revenue',
      points: [
        { x: 2023, y: 10, refs: [1], support: 'supported' },
        { x: 2024, y: 12, refs: [2], support: 'unsupported' },
      ],
    },
    { name: 'Share, "core"', points: [{ x: 2024, y: 0.5, refs: [], derived_from: [1, 2], support: 'derived' }] },
  ],
}

describe('chart output', () => {
  it('counts what the check backed and what was computed', () => {
    expect(supportCount([chart])).toEqual({ supported: 1, derived: 1, total: 3 })
    expect(supportLine([chart])).toBe('1 of 3 values supported · 1 computed')
    expect(supportLine([])).toBeNull()
  })

  it('makes one row per x, a field per series', () => {
    expect(chartRows(chart)).toEqual([
      { x: 2023, s0: 10 },
      { x: 2024, s0: 12, s1: 0.5 },
    ])
    expect(pointAt(chart, 1, 2024)?.support).toBe('derived')
    expect(pointAt(chart, 1, 2023)).toBeUndefined()
  })

  it('opens a value at its passage, a computed one at its first input', () => {
    expect(pointPassage(chart.series[0].points[0])).toBe(1)
    expect(pointPassage(chart.series[1].points[0])).toBe(1)
    expect(pointPassage({ x: 1, y: 1, refs: [], support: 'unsupported' })).toBeNull()
  })

  it('exports CSV with quoting and a file name', () => {
    expect(chartCsv(chart)).toBe('Year,Revenue,"Share, ""core"""\n2023,10,\n2024,12,0.5\n')
    expect(chartFileName('Revenue by year!', 'png')).toBe('revenue-by-year.png')
  })
})

describe('proposalKey', () => {
  it('changes with the notebook, the selection, the pages fetched again and the notes, not with their order or spacing', () => {
    const k = proposalKey('n1', ['b', 'a'], ' costs  by year ', ['p'])
    expect(proposalKey('n1', ['a', 'b'], 'costs by year', ['p'])).toBe(k)
    expect(proposalKey('n2', ['a', 'b'], 'costs by year', ['p'])).not.toBe(k)
    expect(proposalKey('n1', ['a'], 'costs by year', ['p'])).not.toBe(k)
    expect(proposalKey('n1', ['a', 'b'], 'costs by month', ['p'])).not.toBe(k)
    expect(proposalKey('n1', ['a', 'b'], 'costs by year')).not.toBe(k)
    // all sources is not the same as a list of them
    expect(proposalKey('n1', undefined, '')).not.toBe(proposalKey('n1', [], ''))
  })
})
