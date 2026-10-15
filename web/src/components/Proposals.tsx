import { useState, type ReactNode } from 'react'
import { useAsync } from '../hooks/useAsync'
import { useEstimate } from '../hooks/useEstimate'
import { t, type MessageKey } from '../i18n'
import { PriceTag } from './PriceTag'

/** The body every propose call takes: how many at most, the notes, and the
 *  selection as Create sends it. */
export interface ProposeBody {
  max: number
  instructions?: string
  source_ids?: string[]
  url_refresh?: string[]
}

interface Props<T extends { id: string; title: string }> {
  /** the message keys' prefix: `<p>.max`, `.find`, `.finding`, `.findHint`, `.none`, `.pick`, `.stale` */
  texts: 'chartOut' | 'tableOut' | 'themeOut'
  /** one billed model call: the candidates and, with none, why */
  propose: (body: ProposeBody) => Promise<{ candidates: T[]; reason: string | null }>
  /** the estimate's action for that call */
  priceAction: 'chart_propose' | 'table_propose' | 'infographic_propose'
  /** how many may be asked for, and how many one output takes */
  limits: { proposeMax: number; proposeDefault: number; pickMax: number }
  /** the notes, which steer the proposal too */
  instructions: string
  /** what the candidates were found for (notebook, sources, pages, notes); a change makes them stale */
  selection: string
  /** the selected sources and the pages to fetch again, sent as on Create */
  sourceIds?: string[]
  urlRefresh?: string[]
  picked: T[]
  onPick: (picked: T[]) => void
  /** the line under a candidate's title, and its small preview */
  meta: (c: T) => ReactNode
  preview: (c: T) => ReactNode
}

/** The step before Create for the kinds made from proposals (charts,
 *  tables, infographic themes): how many at most, "Find …" (one billed
 *  model call; a 402 opens the voucher dialog as everywhere), then the
 *  candidates as small previews, each with a checkbox, all ticked to
 *  start up to what one output takes. Create takes the ticked ones
 *  exactly as proposed. Candidates found for another selection are
 *  neither shown nor sent. */
export function Proposals<T extends { id: string; title: string }>(p: Props<T>) {
  const [max, setMax] = useState(p.limits.proposeDefault)
  const [found, setFound] = useState<{ candidates: T[]; reason: string | null; selection: string } | null>(null)
  // found for another selection: not shown, not sent (the tiles drop the picks themselves)
  const stale = found !== null && found.selection !== p.selection
  const { busy, error, run } = useAsync()
  const price = useEstimate({ action: p.priceAction })
  const k = (key: string) => `${p.texts}.${key}` as MessageKey

  async function find() {
    const notes = p.instructions.trim().replace(/\s+/g, ' ')
    const urlRefresh = p.urlRefresh ?? []
    const r = await run(() =>
      p.propose({
        max,
        ...(notes ? { instructions: notes } : {}),
        ...(p.sourceIds ? { source_ids: p.sourceIds } : {}),
        ...(urlRefresh.length > 0 ? { url_refresh: urlRefresh } : {}),
      }),
    )
    if (r) {
      setFound({ ...r, selection: p.selection })
      p.onPick(r.candidates.slice(0, p.limits.pickMax))
    }
  }

  const isPicked = (c: T) => p.picked.some((x) => x.id === c.id)
  const toggle = (c: T) => p.onPick(isPicked(c) ? p.picked.filter((x) => x.id !== c.id) : p.picked.length < p.limits.pickMax ? [...p.picked, c] : p.picked)

  return (
    <div className="chart-proposals">
      <div className="row">
        <label>
          {t(k('max'))}
          <select value={max} onChange={(e) => setMax(Number(e.target.value))}>
            {Array.from({ length: p.limits.proposeMax }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary" disabled={busy} onClick={() => void find()}>
          {busy ? t(k('finding')) : t(k('find'))}
        </button>
        <PriceTag state={price} />
      </div>
      <p className="muted small">{t(k('findHint'))}</p>
      {error && <p className="error">{error}</p>}
      {stale && found.candidates.length > 0 && <p className="notice small">{t(k('stale'))}</p>}
      {found && !stale && found.candidates.length === 0 && <p className="notice small">{t(k('none'), { reason: found.reason ?? '—' })}</p>}
      {found && !stale && found.candidates.length > 0 && (
        <ul className="proposal-grid">
          {found.candidates.map((c) => (
            <li key={c.id} className={isPicked(c) ? 'picked' : undefined}>
              <label className="proposal">
                <input type="checkbox" checked={isPicked(c)} onChange={() => toggle(c)} aria-label={t(k('pick'), { title: c.title })} />
                <span className="proposal-title">{c.title}</span>
                <span className="muted small">{p.meta(c)}</span>
              </label>
              {p.preview(c)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
