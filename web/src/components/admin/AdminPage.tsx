import { type ReactNode } from 'react'
import { ADMIN_MOCK } from '../../config'
import { ADMIN_PAGES, adminPath, type AdminPageId } from '../../lib/adminPages'
import { t } from '../../i18n'
import { Overview } from './Overview'
import { LoginAttempts, Logins, Users } from './Users'
import { Visits } from './Visits'
import { Vouchers } from './Credits'
import { AllowedSignIn } from './SignIn'
import { SmtpSettings } from './Mail'
import { Access, Bans, Blocks, RateLimit } from './Security'
import { SystemView } from './System'

/** The sections of each admin page. Only the open page is mounted, so a
 *  page loads its own data and nothing else. */
const PAGE_SECTIONS: Record<AdminPageId, (navigate: (path: string) => void) => ReactNode> = {
  overview: (navigate) => <Overview onNavigate={navigate} />,
  users: () => (
    <>
      <Users />
      <Logins />
      <LoginAttempts />
    </>
  ),
  access: () => <AllowedSignIn />,
  credits: () => <Vouchers />,
  security: () => (
    <>
      <RateLimit />
      <Blocks />
      <Bans />
      <Access />
    </>
  ),
  visits: () => <Visits />,
  mail: () => <SmtpSettings />,
  system: () => <SystemView />,
}

interface Props {
  page: AdminPageId
  onNavigate: (path: string) => void
}

/** Admin panel: a few pages under /admin with a sub-navigation, each a
 *  stack of collapsible sections. Only mounted for is_admin; the server
 *  enforces that too (403). */
export function AdminPage({ page, onNavigate }: Props) {
  return (
    <main className="admin">
      <h1>{t('adm.title')}</h1>
      <nav className="subnav" aria-label={t('adm.pages')}>
        {ADMIN_PAGES.map((p) => (
          <a
            key={p.id}
            href={adminPath(p.id)}
            className={p.id === page ? 'active' : undefined}
            aria-current={p.id === page ? 'page' : undefined}
            onClick={(e) => {
              e.preventDefault()
              onNavigate(adminPath(p.id))
            }}
          >
            {p.label}
          </a>
        ))}
      </nav>
      {ADMIN_MOCK && <p className="notice">{t('adm.mock')}</p>}
      {PAGE_SECTIONS[page](onNavigate)}
    </main>
  )
}
