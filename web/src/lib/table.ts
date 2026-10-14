import type { TableContent } from '../api/types'

export type Cell = string | number | null
export type SortDir = 'asc' | 'desc'

/** Numbers before strings, nulls last, stable within equal keys. */
export function sortRows(rows: Cell[][], column: number, dir: SortDir): Cell[][] {
  return sortOrder(rows, column, dir).map((i) => rows[i])
}

/** The rows' indices in sorted order, for what is kept per row beside them
 *  (a row's passages). Stable: equal values keep their order. */
export function sortOrder(rows: Cell[][], column: number, dir: SortDir): number[] {
  const sign = dir === 'asc' ? 1 : -1
  return rows
    .map((r, i) => ({ r, i }))
    .sort((a, b) => {
      const va = a.r[column] ?? null
      const vb = b.r[column] ?? null
      if (va === null || vb === null) return va === vb ? a.i - b.i : va === null ? 1 : -1
      const c = compare(va, vb)
      return c !== 0 ? c * sign : a.i - b.i
    })
    .map((x) => x.i)
}

function compare(a: string | number, b: string | number): number {
  const na = typeof a === 'number' ? a : Number(a)
  const nb = typeof b === 'number' ? b : Number(b)
  const bothNumeric = !Number.isNaN(na) && !Number.isNaN(nb) && String(a).trim() !== '' && String(b).trim() !== ''
  if (bothNumeric) return na - nb
  return String(a).localeCompare(String(b), undefined, { sensitivity: 'base' })
}

/** RFC 4180: quote a field when it contains a comma, a quote or a line break. */
export function toCsv(table: TableContent): string {
  const line = (cells: Cell[]) => cells.map(csvField).join(',')
  return [line(table.columns), ...table.rows.map(line)].join('\r\n') + '\r\n'
}

function csvField(c: Cell): string {
  if (c === null || c === undefined) return ''
  const s = String(c)
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}
