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

export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
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
  )
}
