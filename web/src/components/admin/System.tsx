import { useEffect, useRef, useState } from 'react'
import { admin } from '../../api/admin'
import type { SystemInfo } from '../../api/types'
import { ArchitectureDiagram } from './ArchitectureDiagram'
import { clusterGap, known, shortCommit, versionLine } from '../../lib/build'
import { formatTime } from '../../lib/format'
import { t } from '../../i18n'
import { Section, Table } from './shared'
import { useLoad } from '../../hooks/useLoad'

const SYSTEM_REFRESH_MS = 15_000

/** What runs where: per service its build and health, then the cluster's
 *  pods and deployments, or a note for a local run without a cluster. */
export function SystemView() {
  const { data, setData, error } = useLoad<SystemInfo | null>(admin.system, null)
  const [refreshed, setRefreshed] = useState(() => new Date().toISOString())
  // the picture before the last refresh: restarts that grew since are climbing
  const [previous, setPrevious] = useState<SystemInfo | null>(null)
  const current = useRef(data)
  useEffect(() => {
    current.current = data
  }, [data])

  // the diagram follows the cluster: every 15 s while the tab is visible;
  // a failed refresh keeps the last picture
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.hidden) return
      admin.system().then(
        (s) => {
          setPrevious(current.current)
          setData(s)
          setRefreshed(new Date().toISOString())
        },
        () => {},
      )
    }, SYSTEM_REFRESH_MS)
    return () => clearInterval(timer)
  }, [setData])
  return (
    <>
      <Section title={t('sys.services')}>
        {error && <p className="error">{error}</p>}
        {data && (
          <>
            {versionLine(data.version, data.commit) && <p className="muted small">{versionLine(data.version, data.commit)}</p>}
            <div className="stat-grid">
              {data.services.map((s) => (
                <div key={s.name} className={s.healthy ? 'stat' : 'stat alert'}>
                  <span className="stat-value">{s.name}</span>
                  <span className={`badge ${s.healthy ? 'ready' : 'failed'}`}>{s.healthy ? t('sys.healthy') : t('sys.unhealthy')}</span>
                  <span className="muted small">
                    {t('sys.version')} {known(s.version) ?? t('sys.unknown')} · {t('sys.commit')} {shortCommit(s.commit) ?? t('sys.unknown')}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </Section>
      {data && (
        <Section title={t('arch.title')}>
          <ArchitectureDiagram system={data} previous={previous} />
          <p className="muted small">{t('arch.refreshed', { time: formatTime(refreshed) })}</p>
        </Section>
      )}
      {data && clusterGap(data) === 'no-cluster' && <p className="notice">{t('sys.noCluster')}</p>}
      {data && clusterGap(data) === 'no-role' && <p className="notice">{t('sys.noRole')}</p>}
      {data && clusterGap(data) === null && (
        <>
          <Section title={t('sys.pods')}>
            <Table
              head={[t('sys.col.name'), t('sys.col.service'), t('sys.col.image'), t('sys.col.ready'), t('sys.col.restarts'), t('sys.col.node'), t('sys.col.started')]}
              rows={data.pods.map((p) => [
                p.name,
                p.service,
                p.image_tag ?? '—',
                <span key="ready" className={`badge ${p.ready ? 'ready' : 'failed'}`}>
                  {p.ready ? t('adm.yes') : t('adm.no')}
                </span>,
                p.restarts,
                p.node ?? '—',
                formatTime(p.started_at),
              ])}
            />
          </Section>
          <Section title={t('sys.deployments')}>
            <Table
              head={[t('sys.col.name'), t('sys.col.replicas'), t('sys.col.ready'), t('sys.col.updated')]}
              rows={data.deployments.map((d) => [
                d.name,
                d.replicas,
                <span key="ready" className={`badge ${d.ready === d.replicas ? 'ready' : 'failed'}`}>
                  {d.ready} / {d.replicas}
                </span>,
                d.updated,
              ])}
            />
          </Section>
        </>
      )}
    </>
  )
}
