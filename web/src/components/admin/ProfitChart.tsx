import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ProfitRow } from '../../api/types'
import { useChartColors } from '../../hooks/useChartColors'
import { t } from '../../i18n'

/** Profit per period in the overview's style: charged against model and
 *  infrastructure cost as bars, profit as a line (missing where no
 *  exchange rate is set). In whole currency units. */
export default function ProfitChart({ rows }: { rows: ProfitRow[] }) {
  const c = useChartColors()
  const data = rows.map((r) => ({
    period: r.period,
    charged: r.charged_cents / 100,
    model: r.model_cost_cents / 100,
    infra: r.infra_cost_cents === null ? null : r.infra_cost_cents / 100,
    profit: r.profit_cents === null ? null : r.profit_cents / 100,
  }))
  const axis = { stroke: c.muted, tick: { fill: c.muted, fontSize: 11 } }
  return (
    <div className="chart-card">
      <div className="chart-body">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={c.line} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="period" {...axis} />
            <YAxis {...axis} />
            <Tooltip contentStyle={{ background: c.panel, border: `1px solid ${c.line}`, color: c.fg }} />
            <Legend wrapperStyle={{ color: c.muted, fontSize: 12 }} />
            <Bar dataKey="charged" name={t('fin.col.charged')} fill={c.series[0]} radius={[3, 3, 0, 0]} />
            <Bar dataKey="model" name={t('fin.col.modelCost')} fill={c.series[1]} radius={[3, 3, 0, 0]} />
            <Bar dataKey="infra" name={t('fin.col.infra')} fill={c.series[3]} radius={[3, 3, 0, 0]} />
            <Line type="monotone" dataKey="profit" name={t('fin.col.profit')} stroke={c.series[2]} strokeWidth={2} connectNulls={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
