import { useCallback, useState, type FormEvent } from 'react'
import { admin } from '../../api/admin'
import type { AdminUser, LoginAttempt, LoginEvent, UserRole } from '../../api/types'
import { useAsync } from '../../hooks/useAsync'
import { ROLES, roleOf } from '../../lib/roles'
import { confirmsEmail, deleteFailure } from '../../lib/deleteUser'
import { formatCents, formatTime } from '../../lib/format'
import { t } from '../../i18n'
import { useCanWrite } from './canWrite'
import { Section, Table } from './shared'
import { useLoad } from '../../hooks/useLoad'

const LOGIN_LIMIT = 50

export function Users() {
  const { data, setData, error } = useLoad<AdminUser[]>(admin.listUsers, [])
  const { busy, error: actionError, run } = useAsync()
  const canWrite = useCanWrite()
  const [deleting, setDeleting] = useState<AdminUser | null>(null)

  async function changeRole(u: AdminUser, role: UserRole) {
    if (role === roleOf(u) || !confirm(t('adm.roleConfirm', { email: u.email, role: t(`adm.role.${role}`) }))) return
    // a refusal (the last admin, the demo user) comes back as the service's sentence
    const updated = await run(() => admin.setRole(u.id, role))
    if (updated) setData((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
  }

  return (
    <Section title={t('adm.users', { n: data.length })}>
      {(error ?? actionError) && <p className="error">{error ?? actionError}</p>}
      <Table
        head={[
          t('adm.col.email'),
          t('adm.col.role'),
          t('adm.col.granted'),
          t('adm.col.used'),
          t('adm.col.balance'),
          t('adm.col.lastLogin'),
          t('adm.col.since'),
          '',
        ]}
        rows={data.map((u) => [
          u.email,
          canWrite ? (
            <select key="role" value={roleOf(u)} disabled={busy} aria-label={t('adm.roleOf', { email: u.email })} onChange={(e) => void changeRole(u, e.target.value as UserRole)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`adm.role.${r}`)}
                </option>
              ))}
            </select>
          ) : (
            t(`adm.role.${roleOf(u)}`)
          ),
          formatCents(u.granted_cents),
          formatCents(u.usage_cents),
          formatCents(u.balance_cents),
          formatTime(u.last_login_at),
          formatTime(u.created_at),
          // viewers get no button at all: deleting is not something to see disabled
          canWrite ? (
            <button key="delete" type="button" className="link danger" disabled={busy} aria-label={t('adm.delUser.of', { email: u.email })} onClick={() => setDeleting(u)}>
              {t('common.delete')}
            </button>
          ) : (
            ''
          ),
        ])}
      />
      {deleting && (
        <DeleteUserDialog
          user={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={(id) => {
            setDeleting(null)
            setData((prev) => prev.filter((x) => x.id !== id))
          }}
        />
      )}
    </Section>
  )
}

/** Deleting a user, in the voucher dialog's style: what goes with the
 *  account, and the address typed out before the button works. A failed
 *  step (502) or a refusal (409) is shown here and the dialog stays. */
function DeleteUserDialog({ user, onClose, onDeleted }: { user: AdminUser; onClose: () => void; onDeleted: (id: string) => void }) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ok = confirmsEmail(typed, user.email)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await admin.deleteUser(user.id)
      onDeleted(user.id)
    } catch (err) {
      setError(deleteFailure(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="backdrop" onClick={busy ? undefined : onClose}>
      <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="delete-user-title" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 id="delete-user-title">{t('adm.delUser.title')}</h2>
        <p>{t('adm.delUser.what', { email: user.email })}</p>
        <label>
          {t('adm.delUser.type')}
          <input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={user.email} autoComplete="off" spellCheck={false} />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="row">
          <button type="button" className="secondary" disabled={busy} onClick={onClose}>
            {t('common.close')}
          </button>
          <button type="submit" className="danger" disabled={busy || !ok}>
            {busy ? t('adm.delUser.deleting') : t('adm.delUser.confirm')}
          </button>
        </div>
      </form>
    </div>
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
