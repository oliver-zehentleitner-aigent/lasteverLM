import type { User } from '../api/types'
import { formatCents } from '../lib/format'

interface Props {
  me: User | null
  route: 'home' | 'library' | 'admin'
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
          Library
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
            Admin
          </a>
        )}
      </nav>
      <div className="account">
        {me && (
          <>
            <span className="muted">{me.email}</span>
            <button type="button" className="pill" onClick={onVoucher} title="Redeem a voucher">
              {formatCents(me.balance_cents)}
            </button>
          </>
        )}
        <button type="button" className="link" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </header>
  )
}
