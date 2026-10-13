import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { admin } from '../../api/admin'
import type { AccessEntry, AdminUser, Ban, Block, LoginEvent, Smtp, VisitBucket } from '../../api/types'
import { ADMIN_MOCK } from '../../config'
import { useAsync } from '../../hooks/useAsync'
import { formatCents, formatTime } from '../../lib/format'

const LOGIN_LIMIT = 50
const VISIT_DAYS = 14
const ACCESS_LIMIT = 100

/** Compact admin panel: everything on one page in collapsible sections, so a
 *  maintainer sees the whole state at a glance. Only mounted for is_admin;
 *  the server enforces that too (403). */
export function AdminPage() {
  return (
    <main className="admin">
      <h1>Admin</h1>
      {ADMIN_MOCK && <p className="notice">Showing mock data: the build runs against an in-memory admin API.</p>}
      <Users />
      <Logins />
      <Visits />
      <Vouchers />
      <AllowedDomains />
      <SmtpSettings />
      <Blocks />
      <Bans />
      <Access />
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
              nothing yet
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
    <Section title={`Users (${data.length})`}>
      {error && <p className="error">{error}</p>}
      <Table
        head={['E-mail', 'Admin', 'Balance', 'Used', 'Last login', 'Since']}
        rows={data.map((u) => [
          u.email,
          u.is_admin ? 'yes' : '',
          formatCents(u.balance_cents),
          formatCents(u.usage_cents),
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
    <Section title={`Login log (last ${LOGIN_LIMIT})`}>
      {error && <p className="error">{error}</p>}
      <Table head={['When', 'E-mail']} rows={data.map((e) => [formatTime(e.at), e.email])} />
    </Section>
  )
}

function Visits() {
  const load = useCallback(() => admin.listVisits(VISIT_DAYS), [])
  const { data, error } = useLoad<VisitBucket[]>(load, [])
  return (
    <Section title={`Visits, last ${VISIT_DAYS} days (per day and path, no addresses)`}>
      {error && <p className="error">{error}</p>}
      <Table head={['Day', 'Path', 'Visits', 'Unique']} rows={data.map((v) => [v.day, v.path, v.visits, v.unique])} />
    </Section>
  )
}

function Vouchers() {
  const [amount, setAmount] = useState('10.00')
  const [count, setCount] = useState('1')
  const [codes, setCodes] = useState<string[]>([])
  const { busy, error, run } = useAsync()

  async function create(e: FormEvent) {
    e.preventDefault()
    const cents = Math.round(Number(amount.replace(',', '.')) * 100)
    const n = Number(count)
    if (!Number.isFinite(cents) || cents <= 0 || !Number.isInteger(n) || n <= 0) return
    const created = await run(() => admin.createVouchers(cents, n))
    if (created) setCodes(created)
  }

  return (
    <Section title="Vouchers">
      <form className="row" onSubmit={create}>
        <label>
          Amount (EUR)
          <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label>
          Count
          <input type="number" min={1} max={100} value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <button type="submit" disabled={busy}>
          Create
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {codes.length > 0 && (
        <div className="codes">
          <p className="muted small">Copy these now; they are not shown again.</p>
          <pre>{codes.join('\n')}</pre>
        </div>
      )}
    </Section>
  )
}

function AllowedDomains() {
  const { data, setData, busy, error, run } = useLoad<string[]>(admin.getAllowedDomains, [])
  const [text, setText] = useState<string | null>(null)
  const value = text ?? data.join('\n')

  async function save(e: FormEvent) {
    e.preventDefault()
    const domains = value
      .split(/[\s,]+/)
      .map((d) => d.trim().toLowerCase())
      .filter(Boolean)
    const saved = await run(() => admin.saveAllowedDomains(domains))
    if (saved) {
      setData(saved)
      setText(null)
    }
  }

  return (
    <Section title="Allowed sign-in domains">
      <form onSubmit={save}>
        <p className="muted small">One domain per line. Empty means any address may request a link.</p>
        <textarea rows={4} value={value} onChange={(e) => setText(e.target.value)} spellCheck={false} />
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy || text === null}>
          Save domains
        </button>
      </form>
    </Section>
  )
}

const EMPTY_SMTP: Smtp = { host: '', port: 587, username: '', from_address: '', starttls: true }

function SmtpSettings() {
  const { data, setData, busy, error, run } = useLoad<Smtp>(admin.getSmtp, EMPTY_SMTP)
  const [form, setForm] = useState<Smtp | null>(null)
  const [tested, setTested] = useState(false)
  const f = form ?? data
  const set = (patch: Partial<Smtp>) => setForm({ ...f, ...patch })

  async function save(e: FormEvent) {
    e.preventDefault()
    const saved = await run(() => admin.saveSmtp(f))
    if (saved) {
      setData(saved)
      setForm(null)
    }
  }

  async function test() {
    setTested(false)
    const ok = await run(async () => {
      await admin.testSmtp()
      return true
    })
    if (ok) setTested(true)
  }

  return (
    <Section title="SMTP (sign-in mails)">
      <form className="grid2" onSubmit={save}>
        <label>
          Host
          <input value={f.host} onChange={(e) => set({ host: e.target.value })} />
        </label>
        <label>
          Port
          <input type="number" value={f.port} onChange={(e) => set({ port: Number(e.target.value) })} />
        </label>
        <label>
          Username
          <input value={f.username} onChange={(e) => set({ username: e.target.value })} autoComplete="off" />
        </label>
        <label>
          Password
          <input
            type="password"
            value={f.password ?? ''}
            placeholder="unchanged"
            onChange={(e) => set({ password: e.target.value })}
            autoComplete="new-password"
          />
        </label>
        <label>
          From address
          <input type="email" value={f.from_address} onChange={(e) => set({ from_address: e.target.value })} />
        </label>
        <label className="check">
          <input type="checkbox" checked={f.starttls} onChange={(e) => set({ starttls: e.target.checked })} /> STARTTLS
        </label>
        {error && <p className="error">{error}</p>}
        {tested && <p className="muted">Test mail queued.</p>}
        <div className="row">
          <button type="button" className="secondary" disabled={busy || form !== null} onClick={() => void test()}>
            Send test mail
          </button>
          <button type="submit" disabled={busy || form === null}>
            Save SMTP settings
          </button>
        </div>
      </form>
    </Section>
  )
}

function Blocks() {
  const { data, error } = useLoad<Block[]>(admin.listBlocks, [])
  return (
    <Section title={`Rate-limit blocks (${data.length} active)`}>
      <p className="muted small">Temporary blocks set by the rate limiter; they expire on their own.</p>
      {error && <p className="error">{error}</p>}
      <Table
        head={['Address', 'Strikes', 'Last strike', 'Until']}
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
    if (!confirm(`Lift the ban for ${ip}?`)) return
    const ok = await run(async () => {
      await admin.liftBan(ip)
      return true
    })
    if (ok) setData((prev) => (includeLifted ? prev.map((b) => (b.ip === ip && !b.lifted_at ? { ...b, lifted_at: new Date().toISOString() } : b)) : prev.filter((b) => b.ip !== ip)))
  }

  return (
    <Section title="Bans">
      <p className="muted small">An active ban stays until an admin lifts it, at most 90 days.</p>
      <label className="check">
        <input type="checkbox" checked={includeLifted} onChange={(e) => setIncludeLifted(e.target.checked)} /> Show lifted bans too
      </label>
      {error && <p className="error">{error}</p>}
      <Table
        head={['Address', 'Reason', 'Since', 'Lifted', '']}
        rows={data.map((b) => [
          b.ip,
          b.reason,
          formatTime(b.created_at),
          b.lifted_at ? formatTime(b.lifted_at) : '',
          b.lifted_at ? '' : (
            <button key="lift" type="button" className="link" disabled={busy} onClick={() => void lift(b.ip)}>
              lift
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
    <Section title={`Access log (last ${ACCESS_LIMIT})`} open={false}>
      <p className="muted small">Raw requests from the rate-limiting middleware, with full addresses. Admin only; see the Privacy section of the account service.</p>
      {error && <p className="error">{error}</p>}
      <Table
        head={['When', 'Address', 'Service', 'Request', 'Status', 'User']}
        rows={data.map((a) => [formatTime(a.at), a.ip, a.service, `${a.method} ${a.path}`, a.status, a.user_id ?? ''])}
      />
    </Section>
  )
}
