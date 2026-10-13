import { useState } from 'react'
import { admin } from '../../api/admin'
import type { Smtp } from '../../api/types'
import { useAsync } from '../../hooks/useAsync'
import { t } from '../../i18n'
import { useCanWrite } from './canWrite'
import { Section } from './shared'
import { useLoad } from '../../hooks/useLoad'

export function SmtpSettings() {
  const { data, error: loadError } = useLoad<Smtp | null>(admin.getSmtp, null)
  const { busy, error, run } = useAsync()
  const canWrite = useCanWrite()
  const [sentTo, setSentTo] = useState<string | null>(null)
  const configured = data !== null && data.host !== ''

  async function test() {
    setSentTo(null)
    const r = await run(() => admin.testSmtp())
    if (r) setSentTo(r.sent_to)
  }

  return (
    <Section title={t('adm.smtp')}>
      <p className="muted small">{t('adm.smtpHint')}</p>
      {data && configured ? (
        <dl className="kv">
          <dt>{t('adm.smtp.host')}</dt>
          <dd>{data.host}</dd>
          <dt>{t('adm.smtp.port')}</dt>
          <dd>{data.port}</dd>
          <dt>{t('adm.smtp.username')}</dt>
          <dd>{data.username || '—'}</dd>
          <dt>{t('adm.smtp.from')}</dt>
          <dd>{data.from_address}</dd>
          <dt>{t('adm.smtp.starttls')}</dt>
          <dd>{data.starttls ? t('adm.yes') : t('adm.no')}</dd>
        </dl>
      ) : (
        data && <p>{t('adm.smtp.notConfigured')}</p>
      )}
      {(loadError ?? error) && <p className="error">{loadError ?? error}</p>}
      {sentTo && <p className="muted">{t('adm.smtp.queued', { to: sentTo })}</p>}
      <div className="row">
        <button type="button" className="secondary" disabled={busy || !configured || !canWrite} title={canWrite ? undefined : t('adm.readOnlyTitle')} onClick={() => void test()}>
          {t('adm.smtp.test')}
        </button>
      </div>
    </Section>
  )
}
