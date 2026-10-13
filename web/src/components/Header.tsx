import type { User } from '../api/types'
import { formatCents } from '../lib/format'
import { t } from '../i18n'

interface Props {
  me: User | null
  route: 'home' | 'library' | 'settings' | 'admin'
  onNavigate: (path: string) => void
  onVoucher: () => void
  onLogout: () => void
}

export function Header({ me, route, onNavigate, onVoucher, onLogout }: Props) {
  return (
    <header className="topbar">
      <a
        href="/"
        className="brand"
        onClick={(e) => {
          e.preventDefault()
          onNavigate('/')
        }}
      >
        lasteverLM
      </a>
      <nav>
        <a
          href="/library"
          className={route === 'library' ? 'active' : undefined}
          onClick={(e) => {
            e.preventDefault()
            onNavigate('/library')
          }}
        >
          {t('header.library')}
        </a>
        <a
          href="/settings"
          className={route === 'settings' ? 'active' : undefined}
          onClick={(e) => {
            e.preventDefault()
            onNavigate('/settings')
          }}
        >
          {t('header.settings')}
        </a>
        {me?.is_admin && (
          <a
            href="/admin"
            className={route === 'admin' ? 'active' : undefined}
            onClick={(e) => {
              e.preventDefault()
              onNavigate('/admin')
            }}
          >
            {t('header.admin')}
          </a>
        )}
      </nav>
      <div className="account">
        {me && (
          <>
            <span className="muted">{me.email}</span>
            <button type="button" className="pill" onClick={onVoucher} title={t('header.redeem')}>
              {formatCents(me.balance_cents)}
            </button>
          </>
        )}
        <button type="button" className="link" onClick={onLogout}>
          {t('header.signOut')}
        </button>
      </div>
    </header>
  )
}
