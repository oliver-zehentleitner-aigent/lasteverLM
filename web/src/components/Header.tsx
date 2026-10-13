import { useEffect, useState } from 'react'
import { account } from '../api/account'
import type { User } from '../api/types'
import { t } from '../i18n'
import { versionLine } from '../lib/build'
import { formatCents } from '../lib/format'
import { useMe } from '../hooks/useMe'
import { applyTheme, nextTheme, readStoredTheme, type Theme } from '../lib/theme'

interface Props {
  me: User | null
  route: 'home' | 'library' | 'settings' | 'admin'
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

const THEME_ICON: Record<Theme, string> = { system: '◐', light: '☀', dark: '☾' }

/** Cycles system, light, dark; applies at once and keeps the choice in this
 *  browser and, when signed in, in the account (the shared demo account
 *  cannot store preferences; then it stays in this browser). */
function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme)
  const { me, setMe } = useMe()
  function cycle() {
    const next = nextTheme(theme)
    setTheme(next)
    applyTheme(next)
    if (me) account.savePreferences({ theme: next }).then(setMe, () => {})
  }
  const name = t(`theme.${theme}`)
  return (
    <button type="button" className="icon theme-toggle" title={t('theme.toggle', { theme: name })} aria-label={t('theme.toggle', { theme: name })} onClick={cycle}>
      {THEME_ICON[theme]}
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
        <ThemeToggle />
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
