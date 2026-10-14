import { Suspense, lazy, type MouseEvent } from 'react'
import { admin } from '../../api/admin'
import type { AccountStats, IngestStats, RagStats, SystemInfo } from '../../api/types'
import { ErrorBoundary } from '../ErrorBoundary'
import { adminPath } from '../../lib/adminPages'
import { attentionItems, kpiTiles, systemMeta } from '../../lib/stats'
import { t } from '../../i18n'
import { useLoad } from '../../hooks/useLoad'

// recharts only in the admin overview: its own chunk, loaded on demand
const StatsCharts = lazy(() => import('./StatsCharts'))

/** Numbers from the three services side by side. Each group loads on its
 *  own, so one service that is down shows its error and the rest stays. */
/** The admin landing page: one meta line (build and service health,
 *  linked to System), one row of six numbers, an attention strip only when
 *  something needs an action, then the charts. Nothing is red unless it is
 *  in the attention strip. */
export function Overview({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { data: system } = useLoad<SystemInfo | null>(admin.system, null)
  const { data: account } = useLoad<AccountStats | null>(admin.accountStats, null)
  const { data: ingest } = useLoad<IngestStats | null>(admin.ingestStats, null)
  const { data: rag } = useLoad<RagStats | null>(admin.ragStats, null)
  const meta = system ? systemMeta(system) : null
  const attention = attentionItems(account, system)
  const go = (href: string) => (e: MouseEvent) => {
    e.preventDefault()
    onNavigate(href)
  }

  return (
    <section className="overview">
      <header className="overview-head">
        <h2>{t('adm.overview')}</h2>
        {meta && (
          <a className="overview-meta" href={adminPath('system')} onClick={go(adminPath('system'))}>
            <span className="dots" aria-hidden="true">
              {meta.dots.map((d) => (
                <span key={d.name} className={d.healthy ? 'dot ok' : 'dot down'} title={d.name} />
              ))}
            </span>
            {[meta.build, meta.health].filter(Boolean).join(' · ')}
          </a>
        )}
      </header>
      <div className="kpi-row">
        {kpiTiles(account, ingest, rag).map((k) => (
          <div key={k.key} className="kpi">
            <span className="kpi-value">{k.value}</span>
            {k.href ? (
              <a className="kpi-label" href={k.href} onClick={go(k.href)}>
                {k.label}
              </a>
            ) : (
              <span className="kpi-label">{k.label}</span>
            )}
            {k.detail && <span className="kpi-detail">{k.detail}</span>}
          </div>
        ))}
      </div>
      {attention.length > 0 && (
        <div className="attention" role="status">
          <strong>{t('att.title')}</strong>
          <ul>
            {attention.map((a) => (
              <li key={a.key}>
                <a href={a.href} onClick={go(a.href)}>
                  {a.text}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      <ErrorBoundary what={t('adm.charts')}>
        <Suspense fallback={<p className="muted small">{t('adm.loadingCharts')}</p>}>
          <StatsCharts />
        </Suspense>
      </ErrorBoundary>
    </section>
  )
}
