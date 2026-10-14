import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import type { ChartPoint, ChartSpec } from '../../api/types'
import type { ChartColors } from '../../hooks/useChartColors'
import { chartRows, pointAt } from '../../lib/chartOutput'

interface Props {
  chart: ChartSpec
  colors: ChartColors
  height: number
  /** small previews: no axes' labels, no tooltip, no clicks */
  compact?: boolean
  onPoint?: (p: ChartPoint, series: string) => void
}

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** A value's marker: filled when the check backed it, hollow when it did
 *  not, a diamond when it was computed from other values. */
function Mark({ cx, cy, point, color, colors, onClick }: { cx?: number; cy?: number; point?: ChartPoint; color: string; colors: ChartColors; onClick?: () => void }) {
  if (cx === undefined || cy === undefined || !point) return null
  const common = { onClick, style: onClick ? { cursor: 'pointer' } : undefined }
  if (point.support === 'derived') {
    const r = 5.5
    return <path {...common} d={`M${cx},${cy - r} L${cx + r},${cy} L${cx},${cy + r} L${cx - r},${cy} Z`} fill={color} stroke={colors.fg} strokeWidth={1} />
  }
  if (point.support === 'unsupported') return <circle {...common} cx={cx} cy={cy} r={4.5} fill={colors.panel} stroke={color} strokeWidth={2} />
  return <circle {...common} cx={cx} cy={cy} r={4.5} fill={color} stroke={color} />
}

/** One chart of a chart output, drawn with recharts in the overview's
 *  style: the theme's series colours, a quiet grid, the values marked by
 *  how well the check backed them. */
export function ChartFigure({ chart, colors, height, compact = false, onPoint }: Props) {
  const color = (i: number) => colors.series[i % colors.series.length]
  const anim = !reduced() && !compact
  const axis = { stroke: colors.muted, tick: { fill: colors.muted, fontSize: compact ? 9 : 11 } }
  const tooltip = compact ? null : <Tooltip contentStyle={{ background: colors.panel, border: `1px solid ${colors.line}`, color: colors.fg }} />
  const click = (p: ChartPoint | undefined, series: string) => (p && onPoint && !compact ? () => onPoint(p, series) : undefined)

  if (chart.chart_type === 'pie') {
    const s = chart.series[0]
    const data = (s?.points ?? []).map((p) => ({ name: String(p.x), value: p.y, point: p }))
    return (
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" outerRadius={compact ? '80%' : '75%'} isAnimationActive={anim} label={!compact} stroke={colors.panel}>
            {data.map((d, i) => (
              <Cell
                key={i}
                fill={d.point.support === 'unsupported' ? colors.panel : color(i)}
                fillOpacity={d.point.support === 'derived' ? 0.55 : 1}
                stroke={d.point.support === 'supported' ? colors.panel : color(i)}
                strokeWidth={d.point.support === 'supported' ? 1 : 2}
                strokeDasharray={d.point.support === 'derived' ? '4 2' : undefined}
                onClick={click(d.point, s?.name ?? '')}
                style={onPoint && !compact ? { cursor: 'pointer' } : undefined}
              />
            ))}
          </Pie>
          {tooltip}
        </PieChart>
      </ResponsiveContainer>
    )
  }

  if (chart.chart_type === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: compact ? 0 : 18, left: compact ? -20 : 0 }}>
          <CartesianGrid stroke={colors.line} strokeDasharray="3 3" />
          <XAxis dataKey="x" type="number" name={chart.x_label} {...axis} label={compact ? undefined : { value: chart.x_label, position: 'insideBottom', offset: -10, fill: colors.muted, fontSize: 11 }} />
          <YAxis dataKey="y" type="number" name={chart.y_label} {...axis} />
          {tooltip}
          {chart.series.map((s, i) => (
            <Scatter
              key={i}
              name={s.name}
              data={s.points.map((p) => ({ x: p.x, y: p.y, point: p }))}
              fill={color(i)}
              isAnimationActive={anim}
              shape={(props: { cx?: number; cy?: number; payload?: { point: ChartPoint } }) => (
                <Mark cx={props.cx} cy={props.cy} point={props.payload?.point} color={color(i)} colors={colors} onClick={click(props.payload?.point, s.name)} />
              )}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  const rows = chartRows(chart)
  const margin = { top: 8, right: 12, bottom: compact ? 0 : 18, left: compact ? -20 : 0 }
  const xAxis = <XAxis dataKey="x" {...axis} label={compact ? undefined : { value: chart.x_label, position: 'insideBottom', offset: -10, fill: colors.muted, fontSize: 11 }} />
  const yAxis = <YAxis {...axis} label={compact ? undefined : { value: chart.y_label, angle: -90, position: 'insideLeft', fill: colors.muted, fontSize: 11 }} />

  if (chart.chart_type === 'line') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={rows} margin={margin}>
          <CartesianGrid stroke={colors.line} strokeDasharray="3 3" />
          {xAxis}
          {yAxis}
          {tooltip}
          {chart.series.map((s, i) => (
            <Line
              key={i}
              type="monotone"
              dataKey={`s${i}`}
              name={s.name}
              stroke={color(i)}
              strokeWidth={2}
              isAnimationActive={anim}
              dot={(props: { cx?: number; cy?: number; payload?: { x: string | number }; index?: number }) => {
                const p = props.payload ? pointAt(chart, i, props.payload.x) : undefined
                return <Mark key={`${i}-${props.index}`} cx={props.cx} cy={props.cy} point={p} color={color(i)} colors={colors} onClick={click(p, s.name)} />
              }}
              activeDot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    )
  }

  const stacked = chart.chart_type === 'stacked_bar'
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={margin}>
        <CartesianGrid stroke={colors.line} strokeDasharray="3 3" vertical={false} />
        {xAxis}
        {yAxis}
        {tooltip}
        {chart.series.map((s, i) => (
          <Bar
            key={i}
            dataKey={`s${i}`}
            name={s.name}
            stackId={stacked ? 'all' : undefined}
            fill={color(i)}
            isAnimationActive={anim}
            shape={(props: { x?: number; y?: number; width?: number; height?: number; payload?: { x: string | number } }) => {
              const p = props.payload ? pointAt(chart, i, props.payload.x) : undefined
              const { x = 0, y = 0, width = 0, height = 0 } = props
              const support = p?.support ?? 'supported'
              return (
                <rect
                  x={x}
                  y={y}
                  width={width}
                  height={Math.max(height, 0)}
                  fill={support === 'unsupported' ? colors.panel : color(i)}
                  fillOpacity={support === 'derived' ? 0.55 : 1}
                  stroke={support === 'supported' ? 'none' : color(i)}
                  strokeWidth={2}
                  strokeDasharray={support === 'derived' ? '4 2' : undefined}
                  onClick={click(p, s.name)}
                  style={onPoint && !compact ? { cursor: 'pointer' } : undefined}
                />
              )
            }}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
