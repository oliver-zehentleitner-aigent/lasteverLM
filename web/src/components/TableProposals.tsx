import { rag } from '../api/rag'
import type { OutputOptionsSpec, TableCandidate, ThemeCandidate } from '../api/types'
import { tn } from '../i18n'
import { Proposals } from './Proposals'

interface Props<T> {
  notebookId: string
  spec: OutputOptionsSpec | null
  instructions: string
  selection: string
  sourceIds?: string[]
  urlRefresh?: string[]
  picked: T[]
  onPick: (picked: T[]) => void
}

/** at most this many per output, as rag takes them */
const MAX = 6

const sourcesOf = (c: { sources: { name: string }[] }) => tn('proposal.sources', c.sources.length, { names: c.sources.map((s) => s.name).join(', ') })

/** The table kind's proposal step: each candidate's columns and up to
 *  three rows as preview, and which sources it rests on. */
export function TableProposals({ notebookId, spec, ...rest }: Props<TableCandidate>) {
  const lim = spec?.proposals?.table ?? { max: MAX, default: MAX }
  return (
    <Proposals
      texts="tableOut"
      propose={(body) => rag.proposeTables(notebookId, body)}
      priceAction="table_propose"
      limits={{ proposeMax: lim.max, proposeDefault: lim.default, pickMax: lim.max }}
      {...rest}
      meta={(c) => (
        <>
          {tn('tableOut.columns', c.columns.length)} · {sourcesOf(c)}
        </>
      )}
      preview={(c) => (
        <table className="proposal-table small">
          <thead>
            <tr>
              {c.columns.map((col, i) => (
                <th key={i}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {c.preview.slice(0, 3).map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    />
  )
}

/** The infographic kind's proposal step: each theme's headline and up to
 *  four facts as preview, and which sources it rests on. */
export function ThemeProposals({ notebookId, spec, ...rest }: Props<ThemeCandidate>) {
  const lim = spec?.proposals?.infographic ?? { max: MAX, default: MAX }
  return (
    <Proposals
      texts="themeOut"
      propose={(body) => rag.proposeThemes(notebookId, body)}
      priceAction="infographic_propose"
      limits={{ proposeMax: lim.max, proposeDefault: lim.default, pickMax: lim.max }}
      {...rest}
      meta={(c) => sourcesOf(c)}
      preview={(c) => (
        <div className="proposal-theme small">
          <p className="proposal-headline">{c.headline}</p>
          <ul>
            {c.facts.slice(0, 4).map((f, i) => (
              <li key={i}>
                <strong>{f.value}</strong> {f.label}
              </li>
            ))}
          </ul>
        </div>
      )}
    />
  )
}

