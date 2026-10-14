import { type ReactNode } from 'react'
import { t } from '../../i18n'

export function Section({ title, children, open = true }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="card" open={open}>
      <summary>{title}</summary>
      {children}
    </details>
  )
}

/** A table that scrolls sideways inside its card when it is wider than
 *  the screen, instead of widening the page. */
export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c}</td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="muted" colSpan={head.length}>
                {t('adm.nothingYet')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
