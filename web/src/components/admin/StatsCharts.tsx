import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { admin } from '../../api/admin'
import { useAsync } from '../../hooks/useAsync'
import {
  SOURCE_SERIES,
  activitySeries,
  costSeries,
  modelSeries,
  outputsByKind,
  ragActivitySeries,
  sourcesSeries,
  total,
} from '../../lib/charts'
import { formatCents } from '../../lib/format'

const DAYS = 30

/** One request per endpoint, shared by every chart that reads it; each
 *  chart still loads and fails on its own. */
function once<T>(load: () => Promise<T>): () => Promise<T> {
  let p: Promise<T> | null = null
  return () => (p ??= load())
}

/** The theme's colours as values: recharts writes them into SVG attributes,
 *  where CSS variables do not resolve. Read once per mount. */
function useColors() {
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement)
    const v = (name: string) => css.getPropertyValue(name).trim()
    return {
      fg: v('--fg'),
      muted: v('--muted'),
      line: v('--line'),
      panel: v('--panel'),
      series: [1, 2, 3, 4, 5, 6].map((i) => v(`--chart-${i}`)),
    }
  }, [])
}

type Colors = ReturnType<typeof useColors>

function useSeries<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const { busy, error, run } = useAsync()
  useEffect(() => {
    void run(async () => setData(await load()))
  }, [load, run])
  return { data, busy, error }
}

function Card({
  title,
  headline,
  wide,
  state,
  children,
}: {
  title: string
  headline?: string
  wide?: boolean
  state: { busy: boolean; error: string | null; ready: boolean }
  children: ReactNode
}) {
  return (
    <section className={wide ? 'chart-card wide' : 'chart-card'}>
      <header>
        <h3>{title}</h3>
        {headline && <span className="headline">{headline}</span>}
      </header>
      {state.error && <p className="error small">{state.error}</p>}
      {!state.ready && !state.error && <p className="muted small">Loading…</p>}
      {state.ready && children}
    </section>
  )
}

const axis = (c: Colors) => ({ stroke: c.line, tick: { fill: c.muted, fontSize: 11 }, tickLine: false })
const tooltip = (c: Colors) => ({
  contentStyle: { background: c.panel, border: `1px solid ${c.line}`, borderRadius: 6, color: c.fg },
  labelStyle: { color: c.fg },
  cursor: { fill: c.line, opacity: 0.4 },
})
const legend = (c: Colors) => ({ wrapperStyle: { color: c.muted, fontSize: 12 } })

/** The statistics part of the admin overview: daily series of the last 30
 *  days from the three services, each chart independent of the others. */
export default function StatsCharts() {
  const c = useColors()
  const loaders = useMemo(
    () => ({
      accountDaily: once(() => admin.accountDaily(DAYS)),
      accountUsage: once(() => admin.accountUsage()),
      ingestDaily: once(() => admin.ingestDaily(DAYS)),
      ragDaily: once(() => admin.ragDaily(DAYS)),
    }),
    [],
  )
  const accountDaily = useSeries(loaders.accountDaily)
  const accountUsage = useSeries(loaders.accountUsage)
  const ingestDaily = useSeries(loaders.ingestDaily)
  const ragDaily = useSeries(loaders.ragDaily)
  const st = <T,>(s: { data: T | null; busy: boolean; error: string | null }) => ({ busy: s.busy, error: s.error, ready: s.data !== null })

  const cost = accountDaily.data ? costSeries(accountDaily.data) : []
  const activity = accountDaily.data ? activitySeries(accountDaily.data) : []
  const docs = ragDaily.data ? ragActivitySeries(ragDaily.data) : []
  const kinds = ragDaily.data ? outputsByKind(ragDaily.data) : []
  const sources = ingestDaily.data ? sourcesSeries(ingestDaily.data) : []
  const models = accountUsage.data ? modelSeries(accountUsage.data) : []

  return (
    <div className="charts">
      <Card
        title={`Cost per day, last ${DAYS} days`}
        headline={accountDaily.data ? formatCents(total(accountDaily.data, (d) => d.usage_cost_cents)) : undefined}
        wide
        state={st(accountDaily)}
      >
        <div className="chart-body">
          <ResponsiveContainer>
            <BarChart data={cost}>
              <CartesianGrid stroke={c.line} vertical={false} />
              <XAxis dataKey="day" {...axis(c)} minTickGap={16} />
              <YAxis {...axis(c)} width={40} unit=" €" />
              <Tooltip {...tooltip(c)} formatter={(v) => `${Number(v).toFixed(2)} €`} />
              <Legend {...legend(c)} />
              <Bar dataKey="cost" name="Usage cost" fill={c.series[0]} radius={[3, 3, 0, 0]} />
              <Bar dataKey="granted" name="Credit granted" fill={c.series[2]} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card
        title="Logins and visits"
        headline={accountDaily.data ? `${total(accountDaily.data, (d) => d.logins)} logins` : undefined}
        state={st(accountDaily)}
      >
        <div className="chart-body">
          <ResponsiveContainer>
            <LineChart data={activity}>
              <CartesianGrid stroke={c.line} vertical={false} />
              <XAxis dataKey="day" {...axis(c)} minTickGap={16} />
              <YAxis {...axis(c)} width={32} allowDecimals={false} />
              <Tooltip {...tooltip(c)} cursor={{ stroke: c.line }} />
              <Legend {...legend(c)} />
              <Line type="monotone" dataKey="visits" name="Visits" stroke={c.series[1]} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="logins" name="Logins" stroke={c.series[0]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card
        title="Chat and documents"
        headline={ragDaily.data ? `${total(ragDaily.data, (d) => d.messages)} messages` : undefined}
        state={st(ragDaily)}
      >
        <div className="chart-body">
          <ResponsiveContainer>
            <AreaChart data={docs}>
              <CartesianGrid stroke={c.line} vertical={false} />
              <XAxis dataKey="day" {...axis(c)} minTickGap={16} />
              <YAxis {...axis(c)} width={32} allowDecimals={false} />
              <Tooltip {...tooltip(c)} cursor={{ stroke: c.line }} />
              <Legend {...legend(c)} />
              <Area type="monotone" dataKey="messages" name="Messages" stroke={c.series[3]} fill={c.series[3]} fillOpacity={0.25} />
              <Area type="monotone" dataKey="documents" name="Documents" stroke={c.series[4]} fill={c.series[4]} fillOpacity={0.25} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card
        title="Documents by kind"
        headline={ragDaily.data ? `${total(kinds, (k) => k.value)} in ${DAYS} days` : undefined}
        state={st(ragDaily)}
      >
        <div className="chart-body">
          {kinds.length === 0 ? (
            <p className="muted small">No documents in this period.</p>
          ) : (
            <ResponsiveContainer>
              <PieChart>
                <Pie data={kinds} dataKey="value" nameKey="name" innerRadius="55%" outerRadius="85%" paddingAngle={2} stroke={c.panel}>
                  {kinds.map((k, i) => (
                    <Cell key={k.kind} fill={c.series[i % c.series.length]} />
                  ))}
                </Pie>
                <Tooltip {...tooltip(c)} />
                <Legend {...legend(c)} layout="vertical" align="right" verticalAlign="middle" />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      <Card
        title="Sources added per day"
        headline={ingestDaily.data ? `${total(ingestDaily.data, (d) => d.sources_created)} added` : undefined}
        wide
        state={st(ingestDaily)}
      >
        <div className="chart-body">
          <ResponsiveContainer>
            <BarChart data={sources}>
              <CartesianGrid stroke={c.line} vertical={false} />
              <XAxis dataKey="day" {...axis(c)} minTickGap={16} />
              <YAxis {...axis(c)} width={32} allowDecimals={false} />
              <Tooltip {...tooltip(c)} />
              <Legend {...legend(c)} />
              {SOURCE_SERIES.map((s, i) => (
                <Bar key={s.key} dataKey={s.key} name={s.label} stackId="sources" fill={c.series[i]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card
        title="Cost by model"
        headline={accountUsage.data ? formatCents(total(accountUsage.data.by_model, (m) => m.cost_cents)) : undefined}
        state={st(accountUsage)}
      >
        <div className="chart-body">
          <ResponsiveContainer>
            <BarChart data={models} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid stroke={c.line} horizontal={false} />
              <XAxis type="number" {...axis(c)} unit=" €" />
              <YAxis type="category" dataKey="name" {...axis(c)} width={150} />
              <Tooltip {...tooltip(c)} formatter={(v) => `${Number(v).toFixed(2)} €`} />
              <Bar dataKey="cost" name="Cost" fill={c.series[5]} radius={[0, 3, 3, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card title="Top users by usage" state={st(accountUsage)}>
        <table className="top-users">
          <thead>
            <tr>
              <th>User</th>
              <th>Used</th>
              <th>Balance</th>
            </tr>
          </thead>
          <tbody>
            {(accountUsage.data?.top_users ?? []).map((u) => (
              <tr key={u.email}>
                <td className="name">{u.email}</td>
                <td>{formatCents(u.usage_cents)}</td>
                <td>{formatCents(u.balance_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
