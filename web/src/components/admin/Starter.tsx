import { useCallback } from 'react'
import { admin } from '../../api/admin'
import { ingest } from '../../api/ingest'
import type { StarterNotebook } from '../../api/types'
import { useAsync } from '../../hooks/useAsync'
import { useLoad } from '../../hooks/useLoad'
import { t } from '../../i18n'
import { formatTime } from '../../lib/format'
import { writeLastNotebook } from '../../lib/lastNotebook'
import { useCanWrite } from './canWrite'
import { Section } from './shared'

/** Which notebook every new account gets a copy of: its title (when it is
 *  one of this admin's own notebooks, the only ones the list can name),
 *  who set it and when, a link that opens it, and Remove. Without one,
 *  how to choose it. */
export function StarterSetting({ onNavigate }: { onNavigate: (path: string) => void }) {
  const canWrite = useCanWrite()
  const load = useCallback(async () => {
    const [starter, mine] = await Promise.all([admin.getStarter(), ingest.listNotebooks().catch(() => [])])
    return { starter, title: mine.find((n) => n.id === starter.notebook_id)?.title ?? null }
  }, [])
  const { data, setData, error } = useLoad<{ starter: StarterNotebook; title: string | null } | null>(load, null)
  const { busy, error: actionError, run } = useAsync()

  async function remove() {
    if (!confirm(t('starter.removeConfirm'))) return
    const ok = await run(() => admin.clearStarter().then(() => true))
    if (ok) setData({ starter: { notebook_id: null, owner_id: null, set_at: null, set_by: null }, title: null })
  }

  const s = data?.starter
  return (
    <Section title={t('starter.title')}>
      <p className="muted small">{t('starter.intro')}</p>
      {(error ?? actionError) && <p className="error">{error ?? actionError}</p>}
      {s && !s.notebook_id && <p>{t('starter.none')}</p>}
      {s?.notebook_id && (
        <p>
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault()
              writeLastNotebook(s.notebook_id as string)
              onNavigate('/')
            }}
          >
            {data?.title ?? s.notebook_id}
          </a>
          {s.set_by && <span className="muted small"> · {t('starter.setBy', { by: s.set_by, at: s.set_at ? formatTime(s.set_at) : '' })}</span>}{' '}
          {canWrite && (
            <button type="button" className="link small" disabled={busy} onClick={() => void remove()}>
              {t('starter.remove')}
            </button>
          )}
        </p>
      )}
    </Section>
  )
}
