import { describe, expect, it } from 'vitest'
import { sortRows, toCsv } from './table'

describe('sortRows', () => {
  const rows = [
    ['b', 10],
    ['a', 2],
    ['c', null],
    ['a', 1],
  ]
  it('sorts numerically when both cells are numbers and keeps nulls last', () => {
    expect(sortRows(rows, 1, 'asc').map((r) => r[1])).toEqual([1, 2, 10, null])
    expect(sortRows(rows, 1, 'desc').map((r) => r[1])).toEqual([10, 2, 1, null])
  })
  it('sorts strings case-insensitively and is stable', () => {
    expect(sortRows(rows, 0, 'asc')).toEqual([
      ['a', 2],
      ['a', 1],
      ['b', 10],
      ['c', null],
    ])
  })
  it('treats numeric strings as numbers', () => {
    expect(sortRows([['10'], ['9'], ['100']], 0, 'asc').map((r) => r[0])).toEqual(['9', '10', '100'])
  })
})

describe('toCsv', () => {
  it('quotes commas, quotes and line breaks, and writes CRLF', () => {
    const csv = toCsv({ columns: ['name', 'note'], rows: [['a,b', 'say "hi"'], ['plain', null], ['multi\nline', 3]] })
    expect(csv).toBe('name,note\r\n"a,b","say ""hi"""\r\nplain,\r\n"multi\nline",3\r\n')
  })
})
