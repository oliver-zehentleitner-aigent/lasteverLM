import type { Dependency, SystemInfo } from '../../api/types'
import { t } from '../../i18n'
import { architectureNodes, dependencyState, ingressState, type DeploymentName, type NodeHealth, type NodeState } from '../../lib/architecture'
import { formatTime } from '../../lib/format'

/** Box positions in the 760 x 420 drawing; the layout is static, the
 *  numbers in the boxes are live. */
const W = 150
const H = 58
const BOX: Record<DeploymentName, { x: number; y: number }> = {
  web: { x: 20, y: 140 },
  account: { x: 210, y: 140 },
  ingest: { x: 400, y: 140 },
  rag: { x: 590, y: 140 },
  'ingest-worker': { x: 400, y: 236 },
  'rag-worker': { x: 590, y: 236 },
}
const EXT = {
  postgres: { x: 20, y: 344, w: 230 },
  storage: { x: 290, y: 344, w: 180 },
  inference: { x: 510, y: 344, w: 230 },
}
const BUS = 322
const cx = (n: DeploymentName) => BOX[n].x + W / 2

/** The running system as a diagram: who talks to whom, with the replicas,
 *  build and health of each deployment filled in from the System data and
 *  each box coloured by its state (see `architectureNodes`); the lines into
 *  a box that is down are drawn dashed red. The external services take
 *  the colour the services' healthz report for them, grey until any does. */
export function ArchitectureDiagram({ system, previous = null }: { system: SystemInfo; previous?: SystemInfo | null }) {
  const nodes = architectureNodes(system, previous)
  const ingress = ingressState(system)
  const ing = system.ingress
  const line = (n: DeploymentName, soft = false) => ['arch-line', soft ? 'soft' : '', nodes[n].state === 'down' ? 'down' : ''].filter(Boolean).join(' ')
  return (
    <div className="arch-wrap">
      <svg className="arch" viewBox="0 0 760 420" role="img" aria-label={t('arch.label')}>
        <defs>
          <marker id="arch-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="arch-head" />
          </marker>
        </defs>

        {/* browser and ingress */}
        <rect className="arch-box ext" x={305} y={6} width={150} height={32} rx={6} />
        <text className="arch-title" x={380} y={27} textAnchor="middle">
          {t('arch.browser')}
        </text>
        <line className="arch-line" x1={380} y1={38} x2={380} y2={62} markerEnd="url(#arch-arrow)" />
        <g className={`arch-node state-${ingress.state}`}>
          <title>
            {ing
              ? [t('arch.ingressProbe', { url: ing.url, at: formatTime(ing.checked_at) }), ing.error, ingress.expiresSoon ? t('arch.tlsSoon') : null].filter(Boolean).join('\n')
              : t('arch.notProbed', { name: t('arch.ingress') })}
          </title>
          <rect className="arch-box" x={260} y={64} width={240} height={40} rx={6} />
          <text className="arch-title" x={380} y={ingress.line ? 81 : 89} textAnchor="middle">
            {t('arch.ingress')}
          </text>
          {ingress.line && (
            <text className="arch-meta" x={380} y={97} textAnchor="middle">
              {t('arch.tlsUntil', { date: ingress.line })}
            </text>
          )}
        </g>
        {(['web', 'account', 'ingest', 'rag'] as const).map((n) => (
          <path key={n} className={line(n)} d={`M380,104 V122 H${cx(n)} V138`} markerEnd="url(#arch-arrow)" />
        ))}

        {/* account, ingest and rag reach PostgreSQL over one bus; the workers' job queue is there too */}
        <path className={line('account')} d={`M${cx('account')},198 V${BUS}`} />
        <path className={line('ingest')} d={`M400,176 H380 V${BUS}`} />
        <path className={line('rag')} d={`M590,176 H570 V${BUS}`} />
        <path className={line('ingest-worker')} d={`M${cx('ingest-worker')},294 V${BUS}`} markerStart="url(#arch-arrow)" />
        <path className={line('rag-worker')} d={`M${cx('rag-worker')},294 V${BUS}`} markerStart="url(#arch-arrow)" />
        <path className="arch-line" d={`M${cx('rag-worker')},${BUS} H${EXT.postgres.x + EXT.postgres.w / 2} V342`} markerEnd="url(#arch-arrow)" />

        {/* the workers read and write objects and call the models; rag's API calls them for answers */}
        <path className={line('ingest-worker', true)} d={`M${cx('ingest-worker') - 30},294 V310 H${EXT.storage.x + 60} V342`} markerEnd="url(#arch-arrow)" />
        <path className={line('ingest-worker', true)} d={`M${cx('ingest-worker') + 30},294 V306 H${EXT.inference.x + 40} V342`} markerEnd="url(#arch-arrow)" />
        <path className={line('rag-worker', true)} d={`M${cx('rag-worker') - 30},294 V302 H${EXT.storage.x + 120} V342`} markerEnd="url(#arch-arrow)" />
        <path className={line('rag-worker', true)} d={`M${cx('rag-worker') + 30},294 V342`} markerEnd="url(#arch-arrow)" />
        <path className={line('rag', true)} d={`M740,170 H752 V372 H742`} markerEnd="url(#arch-arrow)" />

        {/* the six deployments, live */}
        {(Object.keys(BOX) as DeploymentName[]).map((n) => {
          const s = nodes[n]
          const { x, y } = BOX[n]
          return (
            <g key={n} className={`arch-node state-${s.state}`}>
              <title>{nodeTitle(n, s)}</title>
              <rect className="arch-box" x={x} y={y} width={W} height={H} rx={6} />
              <text className="arch-title" x={x + 10} y={y + 18}>
                {n}
              </text>
              <text className="arch-meta" x={x + 10} y={y + 35}>
                {s.replicas ? t('arch.ready', { n: s.replicas }) : '—'}
                {s.restarts > 0 ? ` · ${t('arch.restarts', { n: s.restarts })}` : ''}
              </text>
              <text className="arch-meta" x={x + 10} y={y + 50}>
                {s.build ?? ''}
              </text>
            </g>
          )
        })}

        {/* external services */}
        {(
          [
            ['postgres', t('arch.postgres'), t('arch.postgresNote')],
            ['storage', t('arch.storage'), t('arch.storageNote')],
            ['inference', t('arch.inference'), t('arch.inferenceNote')],
          ] as const
        ).map(([key, title, note]) => {
          const e = EXT[key]
          return (
            <g key={key} className={`arch-node state-${dependencyState(system, key as Dependency)}`}>
              <title>
                {dependencyState(system, key as Dependency) === 'unknown'
                  ? t('arch.notProbed', { name: title })
                  : t('arch.depState', { name: title, state: t(`arch.state.${dependencyState(system, key as Dependency)}`) })}
              </title>
              <rect className="arch-box ext" x={e.x} y={e.y} width={e.w} height={H} rx={6} />
              <text className="arch-title" x={e.x + 10} y={e.y + 20}>
                {title}
              </text>
              <text className="arch-meta" x={e.x + 10} y={e.y + 38}>
                {note}
              </text>
              <text className="arch-meta" x={e.x + e.w - 10} y={e.y + 20} textAnchor="end">
                {t('arch.external')}
              </text>
            </g>
          )
        })}
      </svg>
      <p className="arch-legend small muted">
        {(['ok', 'warn', 'down', 'unknown'] as NodeHealth[]).map((s) => (
          <span key={s} className={`legend-item state-${s}`}>
            <span className="swatch" aria-hidden="true" />
            {t(`arch.state.${s}`)}
          </span>
        ))}
      </p>
    </div>
  )
}

/** The box's tooltip: its state and why. */
function nodeTitle(name: string, s: NodeState): string {
  const why = s.reasons.map((r) => t(`arch.why.${r}`)).join(', ')
  return why ? `${name}: ${t(`arch.state.${s.state}`)} (${why})` : `${name}: ${t(`arch.state.${s.state}`)}`
}
