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
import { useChartColors, type ChartColors } from '../../hooks/useChartColors'
import { admin } from '../../api/admin'
import { useAsync } from '../../hooks/useAsync'
import {
  RANGES,
  SOURCE_SERIES,
  activitySeries,
  costSeries,
  defaultRange,
  hasData,
  lastDays,
  modelSeries,
  outputsByKind,
  ragActivitySeries,
  sourcesSeries,
  total,
  type Range,
} from '../../lib/charts'
import { formatCents } from '../../lib/format'
import { t, tn } from '../../i18n'

/** loaded once for the longest range; the shorter one is a slice */
const DAYS = 30

/** One request per endpoint, shared by every chart that reads it; each
 *  chart still loads and fails on its own. */
function once<T>(load: () => Promise<T>): () => Promise<T> {
  let p: Promise<T> | null = null
  return () => (p ??= load())
}

const useColors = useChartColors
type Colors = ChartColors

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
  full,
  state,
  children,
}: {
  title: string
  headline?: string
  /** spans both columns (the top-users table) */
  full?: boolean
  state: { busy: boolean; error: string | null; ready: boolean }
  children: ReactNode
}) {
  return (
    <section className={full ? 'chart-card full' : 'chart-card'}>
      <header>
        <h3>{title}</h3>
        {headline && <span className="headline">{headline}</span>}
      </header>
      {state.error && <p className="error small">{state.error}</p>}
      {!state.ready && !state.error && <p className="muted small">{t('common.loading')}</p>}
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

/** The statistics part of the admin overview: daily series from the three
 *  services in one shared time range (7 days while the deployment is
 *  young, else 30, with a toggle), in a two-column grid of equal cards.
 *  A chart without data is not drawn; one quiet line names those. */
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
  const [chosen, setChosen] = useState<Range | null>(null)
  const st = <T,>(x: { data: T | null; busy: boolean; error: string | null }) => ({ busy: x.busy, error: x.error, ready: x.data !== null })

  // the default range looks at everything that happened per day, whichever series are in
  const perDay = Array.from({ length: DAYS }, (_, i) => {
    const a = accountDaily.data?.[i]
    const r = ragDaily.data?.[i]
    const g = ingestDaily.data?.[i]
    return (a ? a.logins + a.usage_cost_cents + a.credits_granted_cents : 0) + (r ? r.messages + r.outputs : 0) + (g ? g.sources_created : 0)
  })
  const range: Range = chosen ?? defaultRange(perDay)

  const acc = accountDaily.data ? lastDays(accountDaily.data, range) : null
  const ragDays = ragDaily.data ? lastDays(ragDaily.data, range) : null
  const ingDays = ingestDaily.data ? lastDays(ingestDaily.data, range) : null
  const cost = acc ? costSeries(acc) : []
  const activity = acc ? activitySeries(acc) : []
  const docs = ragDays ? ragActivitySeries(ragDays) : []
  const kinds = ragDays ? outputsByKind(ragDays) : []
  const sources = ingDays ? sourcesSeries(ingDays) : []
  const models = accountUsage.data ? modelSeries(accountUsage.data) : []

  /** One card each, in reading order; pairs fill the two columns. */
  const cards: { key: string; title: string; ready: boolean; empty: boolean; node: ReactNode }[] = [
    {
      key: 'cost',
      title: t('chart.costPerDay', { n: range }),
      ready: acc !== null,
      empty: !hasData(cost, ['cost', 'granted']),
      node: (
        <Card title={t('chart.costPerDay', { n: range })} headline={acc ? formatCents(total(acc, (d) => d.usage_cost_cents)) : undefined} state={st(accountDaily)}>
          <div className="chart-body">
            <ResponsiveContainer>
              <BarChart data={cost}>
                <CartesianGrid stroke={c.line} vertical={false} />
                <XAxis dataKey="day" {...axis(c)} minTickGap={16} />
                <YAxis {...axis(c)} width={40} unit=" €" />
                <Tooltip {...tooltip(c)} formatter={(v) => `${Number(v).toFixed(2)} €`} />
                <Legend {...legend(c)} />
                <Bar dataKey="cost" name={t('chart.usageCost')} fill={c.series[0]} radius={[3, 3, 0, 0]} />
                <Bar dataKey="granted" name={t('chart.creditGranted')} fill={c.series[2]} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ),
    },
    {
      key: 'activity',
      title: t('chart.loginsVisits'),
      ready: acc !== null,
      empty: !hasData(activity, ['logins', 'visits']),
      node: (
        <Card title={t('chart.loginsVisits')} headline={acc ? tn('chart.logins', total(acc, (d) => d.logins)) : undefined} state={st(accountDaily)}>
          <div className="chart-body">
            <ResponsiveContainer>
              <LineChart data={activity}>
                <CartesianGrid stroke={c.line} vertical={false} />
                <XAxis dataKey="day" {...axis(c)} minTickGap={16} />
                <YAxis {...axis(c)} width={32} allowDecimals={false} />
                <Tooltip {...tooltip(c)} cursor={{ stroke: c.line }} />
                <Legend {...legend(c)} />
                <Line type="monotone" dataKey="visits" name={t('chart.visits')} stroke={c.series[1]} strokeWidth={2} dot={range === 7} />
                <Line type="monotone" dataKey="logins" name={t('chart.loginsSeries')} stroke={c.series[0]} strokeWidth={2} dot={range === 7} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ),
    },
    {
      key: 'chat',
      title: t('chart.chatDocs'),
      ready: ragDays !== null,
      empty: !hasData(docs, ['messages', 'documents']),
      node: (
        <Card title={t('chart.chatDocs')} headline={ragDays ? tn('chart.messages', total(ragDays, (d) => d.messages)) : undefined} state={st(ragDaily)}>
          <div className="chart-body">
            <ResponsiveContainer>
              <AreaChart data={docs}>
                <CartesianGrid stroke={c.line} vertical={false} />
                <XAxis dataKey="day" {...axis(c)} minTickGap={16} />
                <YAxis {...axis(c)} width={32} allowDecimals={false} />
                <Tooltip {...tooltip(c)} cursor={{ stroke: c.line }} />
                <Legend {...legend(c)} />
                <Area type="monotone" dataKey="messages" name={t('chart.messagesSeries')} stroke={c.series[3]} fill={c.series[3]} fillOpacity={0.25} />
                <Area type="monotone" dataKey="documents" name={t('chart.documentsSeries')} stroke={c.series[4]} fill={c.series[4]} fillOpacity={0.25} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ),
    },
    {
      key: 'sources',
      title: t('chart.sourcesPerDay'),
      ready: ingDays !== null,
      empty: !hasData(sources, SOURCE_SERIES.map((x) => x.key)),
      node: (
        <Card
          title={t('chart.sourcesPerDay')}
          headline={ingDays ? t('chart.added', { n: total(ingDays, (d) => d.sources_created) }) : undefined}
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
                {SOURCE_SERIES.map((x, i) => (
                  <Bar key={x.key} dataKey={x.key} name={x.label} stackId="sources" fill={c.series[i]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ),
    },
    {
      key: 'kinds',
      title: t('chart.docsByKind'),
      ready: ragDays !== null,
      empty: kinds.length === 0,
      node: (
        <Card title={t('chart.docsByKind')} headline={ragDays ? t('chart.inDays', { total: total(kinds, (k) => k.value), n: range }) : undefined} state={st(ragDaily)}>
          <div className="chart-body">
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
          </div>
        </Card>
      ),
    },
    {
      key: 'models',
      title: t('chart.costByModel'),
      ready: accountUsage.data !== null,
      empty: models.length === 0,
      node: (
        <Card
          title={`${t('chart.costByModel')} · ${t('chart.allTime')}`}
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
                <Bar dataKey="cost" name={t('chart.cost')} fill={c.series[5]} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ),
    },
  ]

  // a loading or failing card keeps its place; an empty one goes to the line below
  const shown = cards.filter((x) => !x.ready || !x.empty)
  const users = accountUsage.data?.top_users ?? []
  const empty = [
    ...cards.filter((x) => x.ready && x.empty).map((x) => x.title),
    ...(accountUsage.data && users.length === 0 ? [t('chart.topUsers')] : []),
  ]

  return (
    <div className="charts-area">
      <div className="charts-toolbar">
        <span className="muted small">{t('chart.range')}</span>
        <span className="presets" role="group" aria-label={t('chart.range')}>
          {RANGES.map((r) => (
            <button key={r} type="button" className={r === range ? 'preset active' : 'preset'} aria-pressed={r === range} onClick={() => setChosen(r)}>
              {t('chart.days', { n: r })}
            </button>
          ))}
        </span>
      </div>
      <div className="charts">
        {shown.map((x) => (
          <div key={x.key} className="chart-slot">
            {x.node}
          </div>
        ))}
        {(users.length > 0 || !accountUsage.data) && (
          <Card full title={`${t('chart.topUsers')} · ${t('chart.allTime')}`} state={st(accountUsage)}>
            <table className="top-users">
              <thead>
                <tr>
                  <th>{t('adm.col.user')}</th>
                  <th>{t('adm.col.used')}</th>
                  <th>{t('adm.col.balance')}</th>
                </tr>
              </thead>
              <tbody>
                {/* a viewer gets addresses masked, and two can mask alike: the position is the key */}
                {users.map((u, i) => (
                  <tr key={i}>
                    <td className="name">{u.email}</td>
                    <td>{formatCents(u.usage_cents)}</td>
                    <td>{formatCents(u.balance_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
      {empty.length > 0 && <p className="muted small">{t('chart.noData', { list: empty.join(', ') })}</p>}
    </div>
  )
}
