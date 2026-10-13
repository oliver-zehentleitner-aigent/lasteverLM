import { useCallback, useEffect, useState } from 'react'
import { account } from './api/account'
import { PAYMENT_REQUIRED, UNAUTHORIZED, apiEvents } from './api/client'
import { getToken, setToken } from './api/token'
import type { User } from './api/types'
import { AdminPage } from './components/admin/AdminPage'
import { AuthCallback } from './components/AuthCallback'
import { Header } from './components/Header'
import { LibraryPage } from './components/LibraryPage'
import { SettingsPage } from './components/SettingsPage'
import { LoginPage } from './components/LoginPage'
import { SharePage } from './components/SharePage'
import { VoucherDialog } from './components/VoucherDialog'
import { Workspace } from './components/Workspace'
import { MeContext } from './hooks/useMe'
import { useRoute } from './hooks/useRoute'
import { writeLastNotebook } from './lib/lastNotebook'
import { setLanguage, t } from './i18n'
import { pickLanguage } from './i18n/translate'

type Session = { state: 'checking' } | { state: 'anonymous' } | { state: 'in'; me: User | null }

export default function App() {
  const { route, navigate } = useRoute()
  const [session, setSession] = useState<Session>(() => (getToken() ? { state: 'checking' } : { state: 'anonymous' }))
  const [voucher, setVoucher] = useState<{ open: boolean; reason: 'manual' | 'exhausted' }>({ open: false, reason: 'manual' })

  // The UI language: the signed-in user's preference, else the browser's.
  // Set before the children render, so every t() in this render uses it.
  const lang = pickLanguage(session.state === 'in' ? session.me?.preferences?.ui_language : null, navigator.languages ?? [])
  setLanguage(lang)
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  /** Load the account behind the stored token. A 401 is handled by the event
   *  below; any other failure keeps the session with an unknown account so
   *  the workspace still works and the panes show the API's error text. */
  const loadMe = useCallback(() => {
    account.me().then(
      (me) => setSession({ state: 'in', me }),
      () => setSession((s) => (s.state === 'anonymous' ? s : { state: 'in', me: null })),
    )
  }, [])

  /** One row per page view in the aggregated visitor log; never blocks the UI. */
  useEffect(() => {
    if (route.name !== 'shared') account.recordVisit(window.location.pathname).catch(() => {})
  }, [route])

  useEffect(() => {
    if (getToken()) loadMe()
  }, [loadMe])

  useEffect(() => {
    const onUnauthorized = () => {
      setToken('')
      setSession({ state: 'anonymous' })
    }
    const onPayment = () => setVoucher({ open: true, reason: 'exhausted' })
    apiEvents.addEventListener(UNAUTHORIZED, onUnauthorized)
    apiEvents.addEventListener(PAYMENT_REQUIRED, onPayment)
    return () => {
      apiEvents.removeEventListener(UNAUTHORIZED, onUnauthorized)
      apiEvents.removeEventListener(PAYMENT_REQUIRED, onPayment)
    }
  }, [])

  const loggedIn = useCallback(() => {
    navigate('/')
    loadMe()
  }, [navigate, loadMe])

  function logout() {
    setToken('')
    setSession({ state: 'anonymous' })
    navigate('/')
  }

  if (route.name === 'shared') return <SharePage token={route.token} />
  if (route.name === 'auth-callback') return <AuthCallback token={route.token} onDone={loggedIn} />
  if (session.state === 'anonymous') return <LoginPage onLoggedIn={loggedIn} />
  if (session.state === 'checking') return <main className="login"><p className="muted">{t('common.loading')}</p></main>

  const me = session.me
  const adminPage = route.name === 'admin' && me?.is_admin ? route.page : null
  const setMe = (u: User) => setSession({ state: 'in', me: u })
  const headerRoute = adminPage ? 'admin' : route.name === 'library' || route.name === 'settings' ? route.name : 'home'

  return (
    <MeContext.Provider value={{ me, setMe }}>
      <Header
        me={me}
        route={headerRoute}
        onNavigate={navigate}
        onVoucher={() => setVoucher({ open: true, reason: 'manual' })}
        onLogout={logout}
      />
      {adminPage ? (
        <AdminPage page={adminPage} onNavigate={navigate} />
      ) : route.name === 'settings' ? (
        <SettingsPage />
      ) : route.name === 'library' ? (
        <LibraryPage
          onOpenNotebook={(id) => {
            writeLastNotebook(id)
            navigate('/')
          }}
        />
      ) : (
        <Workspace />
      )}
      <VoucherDialog
        open={voucher.open}
        reason={voucher.reason}
        onClose={() => setVoucher((v) => ({ ...v, open: false }))}
        onRedeemed={(updated) => {
          setSession({ state: 'in', me: updated })
          setVoucher((v) => ({ ...v, open: false }))
        }}
      />
    </MeContext.Provider>
  )
}
