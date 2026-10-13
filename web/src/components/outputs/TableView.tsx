import { useMemo, useState } from 'react'
import type { TableContent } from '../../api/types'
import { sortRows, toCsv, type SortDir } from '../../lib/table'
import { t } from '../../i18n'

/** Sortable table with CSV export. Sorting is done on a copy; the content
 *  itself is never mutated. */
export function TableView({ content, title }: { content: TableContent; title: string }) {
  const [sort, setSort] = useState<{ column: number; dir: SortDir } | null>(null)
  const rows = useMemo(
    () => (sort ? sortRows(content.rows ?? [], sort.column, sort.dir) : (content.rows ?? [])),
    [content.rows, sort],
  )

  function toggle(column: number) {
    setSort((s) => (s?.column === column ? (s.dir === 'asc' ? { column, dir: 'desc' } : null) : { column, dir: 'asc' }))
  }

  function download() {
    const blob = new Blob([toCsv(content)], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${(title || 'table').replace(/[^\w.-]+/g, '_')}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="datatable">
      <div className="row toolbar no-print">
        <button type="button" className="secondary" onClick={download}>
          {t('table.csv')}
        </button>
      </div>
      <table>
        <thead>
          <tr>
            {(content.columns ?? []).map((c, i) => (
              <th key={i} onClick={() => toggle(i)} aria-sort={sort?.column === i ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                {c}
                {sort?.column === i && <span className="muted"> {sort.dir === 'asc' ? '▲' : '▼'}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c === null || c === undefined ? '' : String(c)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
