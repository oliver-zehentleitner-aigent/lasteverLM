import { useState } from 'react'
import { rag } from '../api/rag'
import type { ChartCandidate, OutputOptionsSpec } from '../api/types'
import { useChartColors } from '../hooks/useChartColors'
import { useAsync } from '../hooks/useAsync'
import { useEstimate } from '../hooks/useEstimate'
import { allPoints, supportLine } from '../lib/chartOutput'
import { t } from '../i18n'
import { ChartFigure } from './charts/ChartFigure'
import { PriceTag } from './PriceTag'

interface Props {
  notebookId: string
  spec: OutputOptionsSpec | null
  /** the notes, which steer the proposal too */
  instructions: string
  /** what the candidates were found for (notebook, sources, notes); a change makes them stale */
  selection: string
  /** the selected sources and the pages to fetch again, sent as on Create */
  sourceIds?: string[]
  urlRefresh?: string[]
  picked: ChartCandidate[]
  onPick: (picked: ChartCandidate[]) => void
}

/** The chart kind's step before Create: how many charts at most, "Find
 *  charts" (one billed model call; a 402 opens the voucher dialog as
 *  everywhere), then the candidates as small previews with their title,
 *  type, number of values and how many the check backed, each with a
 *  checkbox. Create takes the ticked ones exactly as proposed. Loaded on
 *  demand with recharts. */
export default function ChartProposals({ notebookId, spec, instructions, selection, sourceIds, urlRefresh = [], picked, onPick }: Props) {
  const lim = spec?.chart ?? { chart_types: [], charts_max: 12, propose_max: 12, propose_default: 6 }
  const [max, setMax] = useState(lim.propose_default)
  const [found, setFound] = useState<{ candidates: ChartCandidate[]; reason: string | null; selection: string } | null>(null)
  // found for another selection: not shown, not sent (the tiles drop the picks themselves)
  const stale = found !== null && found.selection !== selection
  const { busy, error, run } = useAsync()
  const colors = useChartColors()
  const price = useEstimate({ action: 'chart_propose' })

  async function find() {
    const notes = instructions.trim().replace(/\s+/g, ' ')
    const r = await run(() =>
      rag.proposeCharts(notebookId, {
        max,
        ...(notes ? { instructions: notes } : {}),
        ...(sourceIds ? { source_ids: sourceIds } : {}),
        ...(urlRefresh.length > 0 ? { url_refresh: urlRefresh } : {}),
      }),
    )
    if (r) {
      setFound({ ...r, selection })
      // everything proposed starts ticked, up to the limit of one output
      onPick(r.candidates.slice(0, lim.charts_max))
    }
  }

  const isPicked = (c: ChartCandidate) => picked.some((p) => p.id === c.id)
  const toggle = (c: ChartCandidate) => onPick(isPicked(c) ? picked.filter((p) => p.id !== c.id) : picked.length < lim.charts_max ? [...picked, c] : picked)

  return (
    <div className="chart-proposals">
      <div className="row">
        <label>
          {t('chartOut.max')}
          <select value={max} onChange={(e) => setMax(Number(e.target.value))}>
            {Array.from({ length: lim.propose_max }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary" disabled={busy} onClick={() => void find()}>
          {busy ? t('chartOut.finding') : t('chartOut.find')}
        </button>
        <PriceTag state={price} />
      </div>
      <p className="muted small">{t('chartOut.findHint')}</p>
      {error && <p className="error">{error}</p>}
      {stale && found.candidates.length > 0 && <p className="notice small">{t('chartOut.stale')}</p>}
      {found && !stale && found.candidates.length === 0 && <p className="notice small">{t('chartOut.none', { reason: found.reason ?? '—' })}</p>}
      {found && !stale && found.candidates.length > 0 && (
        <ul className="proposal-grid">
          {found.candidates.map((c) => (
            <li key={c.id} className={isPicked(c) ? 'picked' : undefined}>
              <label className="proposal">
                <input type="checkbox" checked={isPicked(c)} onChange={() => toggle(c)} aria-label={t('chartOut.pick', { title: c.title })} />
                <span className="proposal-title">{c.title}</span>
                <span className="muted small">
                  {t(`chartOut.type.${c.chart_type}`)} · {t('chartOut.points', { n: allPoints(c).length })}
                </span>
                <span className="muted small">{supportLine([c])}</span>
              </label>
              <ChartFigure chart={c} colors={colors} height={110} compact />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
