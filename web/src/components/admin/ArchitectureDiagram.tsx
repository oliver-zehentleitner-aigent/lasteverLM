import type { SystemInfo } from '../../api/types'
import { t } from '../../i18n'
import { architectureNodes, type DeploymentName } from '../../lib/architecture'

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
 *  build and health of each deployment filled in from the System data. A
 *  deployment that is short of replicas or does not answer is drawn in the
 *  attention colour. */
export function ArchitectureDiagram({ system }: { system: SystemInfo }) {
  const nodes = architectureNodes(system)
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
        <rect className="arch-box" x={260} y={64} width={240} height={40} rx={6} />
        <text className="arch-title" x={380} y={89} textAnchor="middle">
          {t('arch.ingress')}
        </text>
        {(['web', 'account', 'ingest', 'rag'] as const).map((n) => (
          <path key={n} className="arch-line" d={`M380,104 V122 H${cx(n)} V138`} markerEnd="url(#arch-arrow)" />
        ))}

        {/* account, ingest and rag reach PostgreSQL over one bus; the workers' job queue is there too */}
        <path className="arch-line" d={`M${cx('account')},198 V${BUS}`} />
        <path className="arch-line" d={`M400,176 H380 V${BUS}`} />
        <path className="arch-line" d={`M590,176 H570 V${BUS}`} />
        <path className="arch-line" d={`M${cx('ingest-worker')},294 V${BUS}`} markerStart="url(#arch-arrow)" />
        <path className="arch-line" d={`M${cx('rag-worker')},294 V${BUS}`} markerStart="url(#arch-arrow)" />
        <path className="arch-line" d={`M${cx('rag-worker')},${BUS} H${EXT.postgres.x + EXT.postgres.w / 2} V342`} markerEnd="url(#arch-arrow)" />

        {/* the workers read and write objects and call the models; rag's API calls them for answers */}
        <path className="arch-line soft" d={`M${cx('ingest-worker') - 30},294 V310 H${EXT.storage.x + 60} V342`} markerEnd="url(#arch-arrow)" />
        <path className="arch-line soft" d={`M${cx('ingest-worker') + 30},294 V306 H${EXT.inference.x + 40} V342`} markerEnd="url(#arch-arrow)" />
        <path className="arch-line soft" d={`M${cx('rag-worker') - 30},294 V302 H${EXT.storage.x + 120} V342`} markerEnd="url(#arch-arrow)" />
        <path className="arch-line soft" d={`M${cx('rag-worker') + 30},294 V342`} markerEnd="url(#arch-arrow)" />
        <path className="arch-line soft" d={`M740,170 H752 V372 H742`} markerEnd="url(#arch-arrow)" />

        {/* the six deployments, live */}
        {(Object.keys(BOX) as DeploymentName[]).map((n) => {
          const s = nodes[n]
          const { x, y } = BOX[n]
          return (
            <g key={n} className={s.healthy ? 'arch-node' : 'arch-node down'}>
              <rect className="arch-box" x={x} y={y} width={W} height={H} rx={6} />
              <text className="arch-title" x={x + 10} y={y + 18}>
                {n}
              </text>
              <text className="arch-meta" x={x + 10} y={y + 35}>
                {s.replicas ? t('arch.ready', { n: s.replicas }) : '—'}
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
            <g key={key}>
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
    </div>
  )
}
