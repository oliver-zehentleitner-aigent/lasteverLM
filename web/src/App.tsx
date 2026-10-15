import { useCallback, useEffect, useState } from 'react'
import { account } from './api/account'
import { OPEN_VOUCHER, PAYMENT_REQUIRED, UNAUTHORIZED, apiEvents } from './api/client'
import { getToken, setToken } from './api/token'
import type { User } from './api/types'
import { canSeeAdmin, canWriteAdmin } from './lib/roles'
import { AdminPage } from './components/admin/AdminPage'
import { AuthCallback } from './components/AuthCallback'
import { Header } from './components/Header'
import { LibraryPage } from './components/LibraryPage'
import { SettingsPage } from './components/SettingsPage'
import { CreditsPage } from './components/CreditsPage'
import { HelpPage } from './components/HelpPage'
import { LoginPage } from './components/LoginPage'
import { SharePage, SharedNotebookPage } from './components/SharePage'
import { PriceList, PricesPage } from './components/PricesPage'
import { VoucherDialog } from './components/VoucherDialog'
import { Workspace } from './components/Workspace'
import { MeContext } from './hooks/useMe'
import { useRoute } from './hooks/useRoute'
import { writeLastNotebook, writeOpenOutput } from './lib/lastNotebook'
import { getSavedTheme, setTheme } from './lib/theme'
import { routeTitle, useDocumentTitle } from './lib/docTitle'
import { TOUR_CREDIT, tourEvents } from './lib/tour'
import { setLanguage, t } from './i18n'
import { pickLanguage } from './i18n/translate'

type Session = { state: 'checking' } | { state: 'anonymous' } | { state: 'in'; me: User | null }

export default function App() {
  const { route, navigate } = useRoute()
  const [session, setSession] = useState<Session>(() => (getToken() ? { state: 'checking' } : { state: 'anonymous' }))
  // `tour`: opened by the introduction's credit step, closed when it is left
  const [voucher, setVoucher] = useState<{ open: boolean; reason: 'manual' | 'exhausted'; short?: string | null; tour?: boolean }>({ open: false, reason: 'manual' })

  // The UI language: the signed-in user's preference, else the browser's.
  // Set before the children render, so every t() in this render uses it.
  const lang = pickLanguage(session.state === 'in' ? session.me?.preferences?.ui_language : null, navigator.languages ?? [])
  setLanguage(lang)
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  // the account's saved theme follows the user across browsers (null keeps
  // this browser's); a session override from the header toggle stays on top
  const accountTheme = session.state === 'in' ? session.me?.preferences?.theme : null
  useEffect(() => {
    if (accountTheme && accountTheme !== getSavedTheme()) setTheme(accountTheme)
  }, [accountTheme])

  /** Load the account behind the stored token. A 401 is handled by the event
   *  below; any other failure keeps the session with an unknown account so
   *  the workspace still works and the panes show the API's error text. */
  const loadMe = useCallback(() => {
    account.me().then(
      (me) => setSession({ state: 'in', me }),
      () => setSession((s) => (s.state === 'anonymous' ? s : { state: 'in', me: null })),
    )
  }, [])

  // the browser tab names the page; the workspace and the shared pages name themselves
  useDocumentTitle(routeTitle(route, window.location.pathname, session.state === 'in'))

  /** One row per page view in the aggregated visitor log; never blocks the UI. */
  useEffect(() => {
    if (route.name !== 'shared' && route.name !== 'shared-notebook') account.recordVisit(window.location.pathname).catch(() => {})
  }, [route])

  useEffect(() => {
    if (getToken()) loadMe()
  }, [loadMe])

  useEffect(() => {
    const onUnauthorized = () => {
      setToken('')
      setSession({ state: 'anonymous' })
    }
    const onPayment = (e: Event) => setVoucher({ open: true, reason: 'exhausted', short: e instanceof CustomEvent ? (e.detail as string | null) : null })
    const onOpenVoucher = () => setVoucher({ open: true, reason: 'manual' })
    apiEvents.addEventListener(UNAUTHORIZED, onUnauthorized)
    apiEvents.addEventListener(PAYMENT_REQUIRED, onPayment)
    apiEvents.addEventListener(OPEN_VOUCHER, onOpenVoucher)
    const onTourCredit = (e: Event) =>
      (e as CustomEvent<boolean>).detail ? setVoucher({ open: true, reason: 'manual', tour: true }) : setVoucher((v) => (v.tour ? { open: false, reason: 'manual' } : v))
    tourEvents.addEventListener(TOUR_CREDIT, onTourCredit)
    return () => {
      tourEvents.removeEventListener(TOUR_CREDIT, onTourCredit)
      apiEvents.removeEventListener(UNAUTHORIZED, onUnauthorized)
      apiEvents.removeEventListener(PAYMENT_REQUIRED, onPayment)
      apiEvents.removeEventListener(OPEN_VOUCHER, onOpenVoucher)
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
  if (route.name === 'shared-notebook') return <SharedNotebookPage token={route.token} />
  // public: without a session the reduced header, with one the app's own
  if (route.name === 'prices' && session.state === 'anonymous') return <PricesPage />
  if (route.name === 'auth-callback') return <AuthCallback token={route.token} onDone={loggedIn} />
  if (session.state === 'anonymous') return <LoginPage onLoggedIn={loggedIn} />
  if (session.state === 'checking') return <main className="login"><p className="muted">{t('common.loading')}</p></main>

  const me = session.me
  const adminPage = route.name === 'admin' && canSeeAdmin(me) ? route.page : null
  const setMe = (u: User) => setSession({ state: 'in', me: u })
  const headerRoute = adminPage ? 'admin' : route.name === 'library' || route.name === 'settings' || route.name === 'prices' || route.name === 'credits' || route.name === 'help' ? route.name : 'home'

  return (
    <MeContext.Provider value={{ me, setMe }}>
      <Header
        me={me}
        route={headerRoute}
        onNavigate={navigate}
        onLogout={logout}
      />
      {adminPage ? (
        <AdminPage page={adminPage} canWrite={canWriteAdmin(me)} onNavigate={navigate} />
      ) : route.name === 'prices' ? (
        <main className="prices-page">
          <PriceList />
        </main>
      ) : route.name === 'help' ? (
        <HelpPage />
      ) : route.name === 'credits' ? (
        <CreditsPage onNavigate={navigate} />
      ) : route.name === 'settings' ? (
        <SettingsPage />
      ) : route.name === 'library' ? (
        <LibraryPage
          onOpenSettings={() => navigate('/settings#trash-days')}
          onOpenNotebook={(id, outputId) => {
            writeLastNotebook(id)
            if (outputId) writeOpenOutput(outputId)
            navigate('/')
          }}
        />
      ) : (
        <Workspace />
      )}
      <VoucherDialog
        open={voucher.open}
        reason={voucher.reason}
        short={voucher.short ?? null}
        forTour={voucher.tour ?? false}
        onClose={() => setVoucher((v) => ({ ...v, open: false }))}
        onRedeemed={(updated) => {
          setSession({ state: 'in', me: updated })
          setVoucher((v) => ({ ...v, open: false }))
        }}
      />
    </MeContext.Provider>
  )
}
