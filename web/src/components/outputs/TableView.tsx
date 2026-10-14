import { useMemo, useState } from 'react'
import type { TableContent } from '../../api/types'
import { sortOrder, toCsv, type SortDir } from '../../lib/table'
import { useCite } from '../../hooks/useCite'
import { ClaimMarks } from '../OutputProvenance'
import { t } from '../../i18n'

/** Sortable table with CSV export. Sorting is done on a copy; the content
 *  itself is never mutated. */
export function TableView({ content, title }: { content: TableContent; title: string }) {
  const [sort, setSort] = useState<{ column: number; dir: SortDir } | null>(null)
  // sorted by index, so each row keeps its passages (row_refs, same index)
  const order = useMemo(() => {
    const all = content.rows ?? []
    return sort ? sortOrder(all, sort.column, sort.dir) : all.map((_, i) => i)
  }, [content.rows, sort])
  const cite = useCite()
  const marks = cite !== null && (content.row_refs?.length ?? 0) > 0

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
            {marks && <th className="marks-col" aria-label={t('outProv.rowSources')} />}
          </tr>
        </thead>
        <tbody>
          {order.map((i) => {
            const r = (content.rows ?? [])[i]
            const claim = content.row_refs?.[i]
            return (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j}>{c === null || c === undefined ? '' : String(c)}</td>
                ))}
                {marks && <td className="marks-col">{claim && <ClaimMarks claim={claim} text={r.map((c) => (c === null ? '' : String(c))).join(' ')} />}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
