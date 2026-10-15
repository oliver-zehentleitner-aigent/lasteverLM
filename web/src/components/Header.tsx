import { useCallback, useEffect, useRef, useState } from 'react'
import { account } from '../api/account'
import { openVoucher } from '../api/client'
import type { User } from '../api/types'
import { t } from '../i18n'
import { versionLine } from '../lib/build'
import { formatCents } from '../lib/format'
import { canSeeAdmin } from '../lib/roles'
import { setSessionTheme, systemPrefersDark, toggledTheme, useTheme, useThemeVersion } from '../lib/theme'
import { PopupMenu } from './PopupMenu'
import { TOUR_CREDIT, tourEvents } from '../lib/tour'

interface Props {
  me: User | null
  route: 'home' | 'library' | 'settings' | 'prices' | 'credits' | 'help' | 'admin'
  onNavigate: (path: string) => void
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

export function Header({ me, route, onNavigate, onLogout }: Props) {
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
        {me && (
          <>
            <a
              href="/credits"
              className={route === 'credits' ? 'pill active' : 'pill'}
              title={t('header.creditTitle')}
              onClick={(e) => {
                e.preventDefault()
                onNavigate('/credits')
              }}
            >
              <BalanceValue cents={me.balance_cents} />
            </a>
          </>
        )}
        <ProfileMenu email={me?.email ?? null} onNavigate={onNavigate} onLogout={onLogout} />
        <a
          href="/help"
          className={route === 'help' ? 'icon help-link active' : 'icon help-link'}
          title={t('header.help')}
          aria-label={t('header.help')}
          aria-current={route === 'help' ? 'page' : undefined}
          onClick={(e) => {
            e.preventDefault()
            onNavigate('/help')
          }}
        >
          ?
        </a>
        <ThemeToggle />
      </div>
    </header>
  )
}

/** The account's round icon with the e-mail's first letter: its menu has
 *  the e-mail as a header, then Credits, Redeem voucher (the dialog at
 *  once), Settings and Sign out. */
function ProfileMenu({ email, onNavigate, onLogout }: { email: string | null; onNavigate: (path: string) => void; onLogout: () => void }) {
  const [open, setOpen] = useState(false)
  // opened by the introduction's credit step: no focus taken, none given back
  const [forTour, setForTour] = useState(false)
  const tourOpen = useRef(false)
  const button = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => {
    setOpen(false)
    if (!tourOpen.current) button.current?.focus()
    tourOpen.current = false
    setForTour(false)
  }, [])
  useEffect(() => {
    const onStep = (e: Event) => {
      const on = (e as CustomEvent<boolean>).detail
      tourOpen.current = on
      setForTour(on)
      setOpen(on)
    }
    tourEvents.addEventListener(TOUR_CREDIT, onStep)
    return () => tourEvents.removeEventListener(TOUR_CREDIT, onStep)
  }, [])
  const initial = (email?.trim()[0] ?? '?').toUpperCase()
  return (
    <span className="profile">
      <button
        ref={button}
        type="button"
        className="avatar"
        aria-haspopup="menu"
        aria-expanded={open}
        title={email ?? t('header.account')}
        aria-label={email ? t('header.accountOf', { email }) : t('header.account')}
        onClick={() => setOpen((o) => !o)}
      >
        {initial}
      </button>
      {open && (
        <PopupMenu
          className="profile-menu"
          label={t('header.account')}
          header={email && <span className="muted small" title={email}>{email}</span>}
          onClose={close}
          focusFirst={!forTour}
          items={[
            { label: t('header.credits'), onSelect: () => onNavigate('/credits') },
            { label: t('header.redeem'), id: 'redeem', onSelect: openVoucher },
            { label: t('header.settings'), onSelect: () => onNavigate('/settings') },
            { label: t('header.signOut'), onSelect: onLogout },
          ]}
        />
      )}
    </span>
  )
}

/** The chip's amount: once it changes from the first one shown, each new
 *  amount flashes briefly (remounted by its key so the animation runs
 *  again; none under reduced motion). */
function BalanceValue({ cents }: { cents: number }) {
  const [first, setFirst] = useState<number | null>(null)
  if (first === null) setFirst(cents)
  return (
    <span key={cents} className={first !== null && cents !== first ? 'balance-value changed' : 'balance-value'}>
      {formatCents(cents)}
    </span>
  )
}
