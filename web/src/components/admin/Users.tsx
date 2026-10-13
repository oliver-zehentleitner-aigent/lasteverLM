import { useCallback } from 'react'
import { admin } from '../../api/admin'
import type { AdminUser, LoginAttempt, LoginEvent } from '../../api/types'
import { formatCents, formatTime } from '../../lib/format'
import { t } from '../../i18n'
import { Section, Table } from './shared'
import { useLoad } from '../../hooks/useLoad'

const LOGIN_LIMIT = 50

export function Users() {
  const { data, error } = useLoad<AdminUser[]>(admin.listUsers, [])
  return (
    <Section title={t('adm.users', { n: data.length })}>
      {error && <p className="error">{error}</p>}
      <Table
        head={[
          t('adm.col.email'),
          t('adm.col.admin'),
          t('adm.col.granted'),
          t('adm.col.used'),
          t('adm.col.balance'),
          t('adm.col.lastLogin'),
          t('adm.col.since'),
        ]}
        rows={data.map((u) => [
          u.email,
          u.is_admin ? t('adm.yes') : '',
          formatCents(u.granted_cents),
          formatCents(u.usage_cents),
          formatCents(u.balance_cents),
          formatTime(u.last_login_at),
          formatTime(u.created_at),
        ])}
      />
    </Section>
  )
}

export function Logins() {
  const load = useCallback(() => admin.listLogins(LOGIN_LIMIT), [])
  const { data, error } = useLoad<LoginEvent[]>(load, [])
  return (
    <Section title={t('adm.loginLog', { n: LOGIN_LIMIT })}>
      {error && <p className="error">{error}</p>}
      <Table head={[t('adm.col.when'), t('adm.col.email')]} rows={data.map((e) => [formatTime(e.at), e.email])} />
    </Section>
  )
}

/** Every sign-in link request with its address and IP, so refused tries and
 *  probing are visible; the login log above only has completed sign-ins. */
export function LoginAttempts() {
  const load = useCallback(() => admin.listLoginAttempts(LOGIN_LIMIT), [])
  const { data, error } = useLoad<LoginAttempt[]>(load, [])
  return (
    <Section title={t('adm.attempts', { n: LOGIN_LIMIT })}>
      {error && <p className="error">{error}</p>}
      <Table
        head={[t('adm.col.when'), t('adm.col.email'), t('adm.col.ip'), t('adm.col.outcome')]}
        rows={data.map((a) => [
          formatTime(a.at),
          a.email,
          a.ip,
          <span key="outcome" className={`badge ${a.outcome === 'allowed' ? 'ready' : 'failed'}`}>
            {t(`adm.outcome.${a.outcome}`)}
          </span>,
        ])}
      />
    </Section>
  )
}
