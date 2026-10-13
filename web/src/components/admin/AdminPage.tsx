import { Suspense, lazy, useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { admin } from '../../api/admin'
import type { AccessEntry, AdminUser, AllowKind, Allowlist, Ban, Block, LoginAttempt, LoginEvent, RateLimitRules, RateLimitUpdate, Smtp, SystemInfo, VisitBucket, Voucher } from '../../api/types'
import { ADMIN_MOCK } from '../../config'
import { CopyButton } from '../CopyButton'
import { ErrorBoundary } from '../ErrorBoundary'
import { ADMIN_PAGES, adminPath, type AdminPageId } from '../../lib/adminPages'
import { useAsync } from '../../hooks/useAsync'
import { known, shortCommit, versionLine } from '../../lib/build'
import { formatCents, formatTime } from '../../lib/format'
import { RATE_LIMIT_BOUNDS, describeRateLimit, rateLimitError } from '../../lib/ratelimit'
import { accountTiles, ingestTiles, ragTiles, type StatTile } from '../../lib/stats'
import { t } from '../../i18n'

// recharts only in the admin overview: its own chunk, loaded on demand
const StatsCharts = lazy(() => import('./StatsCharts'))

const LOGIN_LIMIT = 50
const VISIT_DAYS = 14
const ACCESS_LIMIT = 100
const VOUCHER_LIMIT = 100

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

function Section({ title, children, open = true }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="card" open={open}>
      <summary>{title}</summary>
      {children}
    </details>
  )
}

/** Load once on mount, expose the same busy/error/run as useAsync. */
function useLoad<T>(load: () => Promise<T>, initial: T) {
  const [data, setData] = useState<T>(initial)
  const { busy, error, run } = useAsync()
  useEffect(() => {
    void run(async () => setData(await load()))
  }, [load, run])
  return { data, setData, busy, error, run }
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <table>
      <thead>
        <tr>
          {head.map((h) => (
            <th key={h}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {r.map((c, j) => (
              <td key={j}>{c}</td>
            ))}
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td className="muted" colSpan={head.length}>
              {t('adm.nothingYet')}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  )
}

function Users() {
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

function Logins() {
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
function LoginAttempts() {
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

function Visits() {
  const load = useCallback(() => admin.listVisits(VISIT_DAYS), [])
  const { data, error } = useLoad<VisitBucket[]>(load, [])
  return (
    <Section title={t('adm.visits', { n: VISIT_DAYS })}>
      {error && <p className="error">{error}</p>}
      <Table head={[t('adm.col.day'), t('adm.col.path'), t('adm.col.visits'), t('adm.col.unique')]} rows={data.map((v) => [v.day, v.path, v.visits, v.unique])} />
    </Section>
  )
}

/** Numbers from the three services side by side. Each group loads on its
 *  own, so one service that is down shows its error and the rest stays. */
function Overview({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { data: system } = useLoad<SystemInfo | null>(admin.system, null)
  const build = system ? versionLine(system.version, system.commit) : null
  return (
    <Section title={t('adm.overview')}>
      {build && (
        <p className="muted small build-line">
          <a
            href={adminPath('system')}
            onClick={(e) => {
              e.preventDefault()
              onNavigate(adminPath('system'))
            }}
          >
            {build}
          </a>
        </p>
      )}
      <StatGroup title={t('adm.group.accounts')} load={admin.accountStats} tiles={accountTiles} onNavigate={onNavigate} />
      <StatGroup title={t('adm.group.sources')} load={admin.ingestStats} tiles={ingestTiles} onNavigate={onNavigate} />
      <StatGroup title={t('adm.group.notebooks')} load={admin.ragStats} tiles={ragTiles} onNavigate={onNavigate} />
      <ErrorBoundary what={t('adm.charts')}>
        <Suspense fallback={<p className="muted small">{t('adm.loadingCharts')}</p>}>
          <StatsCharts />
        </Suspense>
      </ErrorBoundary>
    </Section>
  )
}

interface StatGroupProps<T> {
  title: string
  load: () => Promise<T>
  tiles: (s: T) => StatTile[]
  onNavigate: (path: string) => void
}

function StatGroup<T>({ title, load, tiles, onNavigate }: StatGroupProps<T>) {
  const { data, busy, error } = useLoad<T | null>(load, null)
  return (
    <div className="stat-group">
      <h3>{title}</h3>
      {error && <p className="error">{error}</p>}
      {!data && !error && busy && <p className="muted small">{t('common.loading')}</p>}
      {data && (
        <div className="stat-grid">
          {tiles(data).map((t) => {
            const className = ['stat', t.alert ? 'alert' : '', t.href ? 'linked' : ''].join(' ').trim()
            const body = (
              <>
                <span className="stat-value">{t.value}</span>
                <span className="stat-label">{t.label}</span>
                {t.detail && <span className="muted small">{t.detail}</span>}
              </>
            )
            const href = t.href
            return href ? (
              <a
                key={t.label}
                href={href}
                className={className}
                onClick={(e) => {
                  e.preventDefault()
                  onNavigate(href)
                }}
              >
                {body}
              </a>
            ) : (
              <div key={t.label} className={className}>
                {body}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function Vouchers() {
  const [amount, setAmount] = useState('5.00')
  const [count, setCount] = useState('1')
  const [codes, setCodes] = useState<string[]>([])
  const [listVersion, setListVersion] = useState(0)
  const { busy, error, run } = useAsync()

  async function create(e: FormEvent) {
    e.preventDefault()
    const cents = Math.round(Number(amount.replace(',', '.')) * 100)
    const n = Number(count)
    if (!Number.isFinite(cents) || cents <= 0 || !Number.isInteger(n) || n <= 0) return
    const created = await run(() => admin.createVouchers(cents, n))
    if (created) {
      setCodes(created)
      setListVersion((v) => v + 1)
    }
  }

  return (
    <Section title={t('adm.vouchers')}>
      <div className="voucher-create">
        <form className="row" onSubmit={create}>
          <label>
            {t('adm.amountEur')}
            <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label>
            {t('adm.count')}
            <input type="number" min={1} max={100} value={count} onChange={(e) => setCount(e.target.value)} />
          </label>
          <button type="submit" disabled={busy}>
            {t('adm.create')}
          </button>
        </form>
        {codes.length > 0 && <VoucherCodes codes={codes} />}
      </div>
      {error && <p className="error">{error}</p>}
      <VoucherList key={listVersion} />
    </Section>
  )
}

/** Fresh codes, shown once: compact chips with a copy button each, and
 *  "copy all" (one per line) when there are several. */
function VoucherCodes({ codes }: { codes: string[] }) {
  const all = useRef<HTMLDivElement>(null)
  return (
    <div className="codes" ref={all} aria-label={t('adm.codes')}>
      <p className="muted small">{t('adm.copyCodes')}</p>
      <ul className="code-chips">
        {codes.map((c) => (
          <CodeChip key={c} code={c} />
        ))}
      </ul>
      {codes.length > 1 && <CopyButton text={codes.join('\n')} target={all} label={t('copy.all')} />}
    </div>
  )
}

function CodeChip({ code }: { code: string }) {
  const el = useRef<HTMLElement>(null)
  return (
    <li className="code-chip">
      <code ref={el}>{code}</code>
      <CopyButton text={code} target={el} />
    </li>
  )
}

const loadVouchers = () => admin.listVouchers(VOUCHER_LIMIT)

/** Issued vouchers, newest first; remounted after a create so the new ones
 *  appear. The codes are never listed: the server keeps only their hashes.
 *  Open vouchers can be deleted; a redeemed one is history and has no button. */
function VoucherList() {
  const { data, setData, error } = useLoad<Voucher[]>(loadVouchers, [])
  const { busy, error: actionError, run } = useAsync()

  async function remove(v: Voucher) {
    if (!confirm(t('adm.voucherDeleteConfirm', { amount: formatCents(v.amount_cents) }))) return
    const ok = await run(async () => {
      await admin.deleteVoucher(v.id)
      return true
    })
    if (ok) setData((list) => list.filter((x) => x.id !== v.id))
  }

  return (
    <>
      {(error ?? actionError) && <p className="error">{error ?? actionError}</p>}
      <Table
        head={[
          t('adm.col.amount'),
          t('adm.col.createdBy'),
          t('adm.col.created'),
          t('adm.col.status'),
          t('adm.col.redeemedBy'),
          t('adm.col.redeemed'),
          '',
        ]}
        rows={data.map((v) => [
          formatCents(v.amount_cents),
          v.created_by,
          formatTime(v.created_at),
          <span key="status" className={`badge ${v.status === 'open' ? 'ready' : ''}`}>
            {t(`status.${v.status}`)}
          </span>,
          v.redeemed_by ?? '—',
          v.redeemed_at ? formatTime(v.redeemed_at) : '—',
          v.status === 'open' ? (
            <button key="delete" type="button" className="link danger" disabled={busy} onClick={() => void remove(v)}>
              {t('common.delete')}
            </button>
          ) : (
            ''
          ),
        ])}
      />
    </>
  )
}

const EMPTY_ALLOWLIST: Allowlist = { allowed_domains: [], allowed_addresses: [] }

/** Two lists edited one entry at a time; every change answers with both
 *  lists as stored (normalized, sorted), which replaces the local copy. */
function AllowedSignIn() {
  const { data, setData, error } = useLoad<Allowlist>(admin.getAllowlist, EMPTY_ALLOWLIST)
  const empty = data.allowed_domains.length === 0 && data.allowed_addresses.length === 0
  return (
    <Section title={t('adm.allowed')}>
      <p className="muted small">
        {t('adm.allowedHint')}
        {empty && t('adm.allowedEmpty')}
      </p>
      {error && <p className="error">{error}</p>}
      <div className="grid2">
        <AllowList kind="domain" title={t('adm.domains')} placeholder="example.org" values={data.allowed_domains} onChange={setData} />
        <AllowList
          kind="address"
          title={t('adm.addresses')}
          placeholder="name@example.org"
          values={data.allowed_addresses}
          onChange={setData}
        />
      </div>
    </Section>
  )
}

interface AllowListProps {
  kind: AllowKind
  title: string
  placeholder: string
  values: string[]
  onChange: (a: Allowlist) => void
}

function AllowList({ kind, title, placeholder, values, onChange }: AllowListProps) {
  const [value, setValue] = useState('')
  const { busy, error, run } = useAsync()

  async function add(e: FormEvent) {
    e.preventDefault()
    if (!value.trim()) return
    const updated = await run(() => admin.addAllowed(kind, value.trim()))
    if (updated) {
      onChange(updated)
      setValue('')
    }
  }

  async function remove(v: string) {
    if (!confirm(t(kind === 'domain' ? 'adm.removeAllowedDomain' : 'adm.removeAllowedAddress', { v }))) return
    const ok = await run(async () => {
      await admin.removeAllowed(kind, v)
      return true
    })
    if (ok) onChange(await admin.getAllowlist())
  }

  return (
    <div className="allow-list">
      <h3>{title}</h3>
      <ul className="list">
        {values.map((v) => (
          <li key={v}>
            <span className="item">{v}</span>
            <button type="button" className="icon" title={t('adm.remove', { v })} disabled={busy} onClick={() => void remove(v)}>
              ×
            </button>
          </li>
        ))}
        {values.length === 0 && <li className="muted small">{t('adm.none')}</li>}
      </ul>
      <form className="row" onSubmit={add}>
        <input
          type={kind === 'address' ? 'email' : 'text'}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          aria-label={t('adm.addTo', { list: title })}
          spellCheck={false}
        />
        <button type="submit" disabled={busy || !value.trim()}>
          {t('common.add')}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  )
}

function SmtpSettings() {
  const { data, error: loadError } = useLoad<Smtp | null>(admin.getSmtp, null)
  const { busy, error, run } = useAsync()
  const [sentTo, setSentTo] = useState<string | null>(null)
  const configured = data !== null && data.host !== ''

  async function test() {
    setSentTo(null)
    const r = await run(() => admin.testSmtp())
    if (r) setSentTo(r.sent_to)
  }

  return (
    <Section title={t('adm.smtp')}>
      <p className="muted small">{t('adm.smtpHint')}</p>
      {data && configured ? (
        <dl className="kv">
          <dt>{t('adm.smtp.host')}</dt>
          <dd>{data.host}</dd>
          <dt>{t('adm.smtp.port')}</dt>
          <dd>{data.port}</dd>
          <dt>{t('adm.smtp.username')}</dt>
          <dd>{data.username || '—'}</dd>
          <dt>{t('adm.smtp.from')}</dt>
          <dd>{data.from_address}</dd>
          <dt>{t('adm.smtp.starttls')}</dt>
          <dd>{data.starttls ? t('adm.yes') : t('adm.no')}</dd>
        </dl>
      ) : (
        data && <p>{t('adm.smtp.notConfigured')}</p>
      )}
      {(loadError ?? error) && <p className="error">{loadError ?? error}</p>}
      {sentTo && <p className="muted">{t('adm.smtp.queued', { to: sentTo })}</p>}
      <div className="row">
        <button type="button" className="secondary" disabled={busy || !configured} onClick={() => void test()}>
          {t('adm.smtp.test')}
        </button>
      </div>
    </Section>
  )
}

const RULE_FIELDS: { key: keyof RateLimitUpdate; label: () => string }[] = [
  { key: 'per_minute', label: () => t('adm.rl.perMinute') },
  { key: 'block_minutes', label: () => t('adm.rl.blockMinutes') },
  { key: 'ban_after_strikes', label: () => t('adm.rl.strikes') },
  { key: 'strike_window_hours', label: () => t('adm.rl.window') },
]

/** The rule behind the blocks and bans below, as a sentence and as the
 *  four numbers an admin may change; every service picks a change up
 *  within 30 seconds. The ban cap and the retention are environment only. */
function RateLimit() {
  const { data, setData, error: loadError } = useLoad<RateLimitRules | null>(admin.getRateLimit, null)
  const [form, setForm] = useState<Record<keyof RateLimitUpdate, string> | null>(null)
  const { busy, error, run } = useAsync()
  const [invalid, setInvalid] = useState<string | null>(null)

  const values = form ?? (data ? toForm(data) : null)

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!values) return
    const update: RateLimitUpdate = {
      per_minute: Number(values.per_minute),
      block_minutes: Number(values.block_minutes),
      ban_after_strikes: Number(values.ban_after_strikes),
      strike_window_hours: Number(values.strike_window_hours),
    }
    const problem = rateLimitError(update)
    setInvalid(problem)
    if (problem) return
    const saved = await run(() => admin.saveRateLimit(update))
    if (saved) {
      setData(saved)
      setForm(null)
    }
  }

  async function reset() {
    if (!confirm(t('adm.rl.resetConfirm'))) return
    const fresh = await run(async () => {
      await admin.resetRateLimit()
      return admin.getRateLimit()
    })
    if (fresh) {
      setData(fresh)
      setForm(null)
      setInvalid(null)
    }
  }

  return (
    <Section title={t('adm.rl.title')}>
      <p className="muted small">{t('adm.rl.ingress')}</p>
      {loadError && <p className="error">{loadError}</p>}
      {data && (
        <>
          <p>{describeRateLimit(data)}</p>
          <p className="muted small">{t('adm.rl.fromEnv', { ban: data.ban_max_days, keep: data.retention_days })}</p>
        </>
      )}
      {values && (
        <form className="grid2" onSubmit={save}>
          {RULE_FIELDS.map((f) => (
            <label key={f.key}>
              {f.label()}
              <input
                type="number"
                min={RATE_LIMIT_BOUNDS[f.key][0]}
                max={RATE_LIMIT_BOUNDS[f.key][1]}
                step={1}
                value={values[f.key]}
                onChange={(e) => setForm({ ...values, [f.key]: e.target.value })}
              />
            </label>
          ))}
          {(invalid ?? error) && <p className="error">{invalid ?? error}</p>}
          <div className="row">
            <button type="button" className="secondary" disabled={busy} onClick={() => void reset()}>
              {t('adm.rl.reset')}
            </button>
            <button type="submit" disabled={busy || form === null}>
              {t('adm.rl.save')}
            </button>
          </div>
          <p className="muted small">{t('adm.rl.applies')}</p>
        </form>
      )}
    </Section>
  )
}

function toForm(r: RateLimitRules): Record<keyof RateLimitUpdate, string> {
  return {
    per_minute: String(r.per_minute),
    block_minutes: String(r.block_minutes),
    ban_after_strikes: String(r.ban_after_strikes),
    strike_window_hours: String(r.strike_window_hours),
  }
}

function Blocks() {
  const { data, error } = useLoad<Block[]>(admin.listBlocks, [])
  return (
    <Section title={t('adm.blocks', { n: data.length })}>
      <p className="muted small">{t('adm.blocksHint')}</p>
      {error && <p className="error">{error}</p>}
      <Table
        head={[t('adm.col.address'), t('adm.col.strikes'), t('adm.col.lastStrike'), t('adm.col.until')]}
        rows={data.map((b) => [b.ip, b.strikes, formatTime(b.updated_at), formatTime(b.blocked_until)])}
      />
    </Section>
  )
}

function Bans() {
  const [includeLifted, setIncludeLifted] = useState(false)
  const load = useCallback(() => admin.listBans(includeLifted), [includeLifted])
  const { data, setData, busy, error, run } = useLoad<Ban[]>(load, [])

  async function lift(ip: string) {
    if (!confirm(t('adm.liftConfirm', { ip }))) return
    const ok = await run(async () => {
      await admin.liftBan(ip)
      return true
    })
    if (ok) setData((prev) => (includeLifted ? prev.map((b) => (b.ip === ip && !b.lifted_at ? { ...b, lifted_at: new Date().toISOString() } : b)) : prev.filter((b) => b.ip !== ip)))
  }

  return (
    <Section title={t('adm.bans')}>
      <p className="muted small">{t('adm.bansHint')}</p>
      <label className="check">
        <input type="checkbox" checked={includeLifted} onChange={(e) => setIncludeLifted(e.target.checked)} /> {t('adm.showLifted')}
      </label>
      {error && <p className="error">{error}</p>}
      <Table
        head={[t('adm.col.address'), t('adm.col.reason'), t('adm.col.since'), t('adm.col.lifted'), '']}
        rows={data.map((b) => [
          b.ip,
          b.reason,
          formatTime(b.created_at),
          b.lifted_at ? formatTime(b.lifted_at) : '',
          b.lifted_at ? '' : (
            <button key="lift" type="button" className="link" disabled={busy} onClick={() => void lift(b.ip)}>
              {t('adm.lift')}
            </button>
          ),
        ])}
      />
    </Section>
  )
}

function Access() {
  const load = useCallback(() => admin.listAccess(ACCESS_LIMIT), [])
  const { data, error } = useLoad<AccessEntry[]>(load, [])
  return (
    <Section title={t('adm.access', { n: ACCESS_LIMIT })} open={false}>
      <p className="muted small">{t('adm.accessHint')}</p>
      {error && <p className="error">{error}</p>}
      <Table
        head={[t('adm.col.when'), t('adm.col.address'), t('adm.col.service'), t('adm.col.request'), t('adm.col.status'), t('adm.col.user')]}
        rows={data.map((a) => [formatTime(a.at), a.ip, a.service, `${a.method} ${a.path}`, a.status, a.user_id ?? ''])}
      />
    </Section>
  )
}

/** What runs where: per service its build and health, then the cluster's
 *  pods and deployments, or a note for a local run without a cluster. */
function SystemView() {
  const { data, error } = useLoad<SystemInfo | null>(admin.system, null)
  return (
    <>
      <Section title={t('sys.services')}>
        {error && <p className="error">{error}</p>}
        {data && (
          <>
            {versionLine(data.version, data.commit) && <p className="muted small">{versionLine(data.version, data.commit)}</p>}
            <div className="stat-grid">
              {data.services.map((s) => (
                <div key={s.name} className={s.healthy ? 'stat' : 'stat alert'}>
                  <span className="stat-value">{s.name}</span>
                  <span className={`badge ${s.healthy ? 'ready' : 'failed'}`}>{s.healthy ? t('sys.healthy') : t('sys.unhealthy')}</span>
                  <span className="muted small">
                    {t('sys.version')} {known(s.version) ?? t('sys.unknown')} · {t('sys.commit')} {shortCommit(s.commit) ?? t('sys.unknown')}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </Section>
      {data && !data.cluster && <p className="notice">{t('sys.noCluster')}</p>}
      {data?.cluster && (
        <>
          <Section title={t('sys.pods')}>
            <Table
              head={[t('sys.col.name'), t('sys.col.service'), t('sys.col.image'), t('sys.col.ready'), t('sys.col.restarts'), t('sys.col.node'), t('sys.col.started')]}
              rows={data.pods.map((p) => [
                p.name,
                p.service,
                p.image_tag ?? '—',
                <span key="ready" className={`badge ${p.ready ? 'ready' : 'failed'}`}>
                  {p.ready ? t('adm.yes') : t('adm.no')}
                </span>,
                p.restarts,
                p.node ?? '—',
                formatTime(p.started_at),
              ])}
            />
          </Section>
          <Section title={t('sys.deployments')}>
            <Table
              head={[t('sys.col.name'), t('sys.col.replicas'), t('sys.col.ready'), t('sys.col.updated')]}
              rows={data.deployments.map((d) => [
                d.name,
                d.replicas,
                <span key="ready" className={`badge ${d.ready === d.replicas ? 'ready' : 'failed'}`}>
                  {d.ready} / {d.replicas}
                </span>,
                d.updated,
              ])}
            />
          </Section>
        </>
      )}
    </>
  )
}
