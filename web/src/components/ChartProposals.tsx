import { rag } from '../api/rag'
import type { ChartCandidate, OutputOptionsSpec } from '../api/types'
import { useChartColors } from '../hooks/useChartColors'
import { allPoints, supportLine } from '../lib/chartOutput'
import { t } from '../i18n'
import { ChartFigure } from './charts/ChartFigure'
import { Proposals } from './Proposals'

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

/** The chart kind's step before Create: the shared proposal step with
 *  each candidate's type, number of values and how many the check backed,
 *  and a small chart as preview. Loaded on demand with recharts. */
export default function ChartProposals({ notebookId, spec, instructions, selection, sourceIds, urlRefresh = [], picked, onPick }: Props) {
  const lim = spec?.chart ?? { chart_types: [], charts_max: 12, propose_max: 12, propose_default: 6 }
  const colors = useChartColors()
  return (
    <Proposals
      texts="chartOut"
      propose={(body) => rag.proposeCharts(notebookId, body)}
      priceAction="chart_propose"
      limits={{ proposeMax: lim.propose_max, proposeDefault: lim.propose_default, pickMax: lim.charts_max }}
      instructions={instructions}
      selection={selection}
      sourceIds={sourceIds}
      urlRefresh={urlRefresh}
      picked={picked}
      onPick={onPick}
      meta={(c) => (
        <>
          {t(`chartOut.type.${c.chart_type}`)} · {t('chartOut.points', { n: allPoints(c).length })} · {supportLine([c])}
        </>
      )}
      preview={(c) => <ChartFigure chart={c} colors={colors} height={110} compact />}
    />
  )
}
