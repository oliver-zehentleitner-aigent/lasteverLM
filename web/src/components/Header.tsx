import { useEffect, useState } from 'react'
import { account } from '../api/account'
import type { User } from '../api/types'
import { t } from '../i18n'
import { versionLine } from '../lib/build'
import { formatCents } from '../lib/format'
import { canSeeAdmin } from '../lib/roles'
import { setSessionTheme, systemPrefersDark, toggledTheme, useTheme, useThemeVersion } from '../lib/theme'

interface Props {
  me: User | null
  route: 'home' | 'library' | 'settings' | 'prices' | 'admin'
  onNavigate: (path: string) => void
  onVoucher: () => void
  onLogout: () => void
}

/** The running build for everyone, as the brand's tooltip; from the
 *  public /healthz, so it needs no admin rights. */
function useBuild(): string | null {
  const [line, setLine] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    account.health().then(
      (h) => live && setLine(versionLine(h.version, h.commit)),
      () => {
        // no build shown; nothing else depends on it
      },
    )
    return () => {
      live = false
    }
  }, [])
  return line
}

/** Switches between light and dark for this browser session, starting
 *  from what is on screen; the icon shows what a click gives. The lasting
 *  choice, "system" included, is made on the settings page. */
function ThemeToggle() {
  const theme = useTheme()
  useThemeVersion()
  const next = toggledTheme(theme, systemPrefersDark())
  const label = next === 'dark' ? t('theme.toDark') : t('theme.toLight')
  return (
    <button type="button" className="icon theme-toggle" title={label} aria-label={label} onClick={() => setSessionTheme(next)}>
      {next === 'dark' ? '☾' : '☀'}
    </button>
  )
}

export function Header({ me, route, onNavigate, onVoucher, onLogout }: Props) {
  const build = useBuild()
  return (
    <header className="topbar">
      <a
        href="/"
        className="brand"
        title={build ? t('header.build', { line: build }) : undefined}
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
        <a
          href="/prices"
          className={route === 'prices' ? 'active' : undefined}
          onClick={(e) => {
            e.preventDefault()
            onNavigate('/prices')
          }}
        >
          {t('header.prices')}
        </a>
        {canSeeAdmin(me) && (
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
        <ThemeToggle />
        {me && (
          <>
            <span className="muted email" title={me.email}>{me.email}</span>
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
