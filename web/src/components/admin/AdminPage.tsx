import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { admin } from '../../api/admin'
import type { AccessEntry, AdminUser, AllowKind, Allowlist, Ban, Block, LoginAttempt, LoginEvent, RateLimitRules, RateLimitUpdate, Smtp, VisitBucket, Voucher } from '../../api/types'
import { ADMIN_MOCK } from '../../config'
import { useAsync } from '../../hooks/useAsync'
import { formatCents, formatTime } from '../../lib/format'
import { RATE_LIMIT_BOUNDS, describeRateLimit, rateLimitError } from '../../lib/ratelimit'
import { accountTiles, ingestTiles, ragTiles, type StatTile } from '../../lib/stats'

const LOGIN_LIMIT = 50
const VISIT_DAYS = 14
const ACCESS_LIMIT = 100
const VOUCHER_LIMIT = 100

/** Compact admin panel: everything on one page in collapsible sections, so a
 *  maintainer sees the whole state at a glance. Only mounted for is_admin;
 *  the server enforces that too (403). */
export function AdminPage() {
  return (
    <main className="admin">
      <h1>Admin</h1>
      {ADMIN_MOCK && <p className="notice">Showing mock data: the build runs against an in-memory admin API.</p>}
      <Overview />
      <Users />
      <Logins />
      <LoginAttempts />
      <Visits />
      <Vouchers />
      <AllowedSignIn />
      <SmtpSettings />
      <RateLimit />
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

/** Every sign-in link request with its address and IP, so refused tries and
 *  probing are visible; the login log above only has completed sign-ins. */
function LoginAttempts() {
  const load = useCallback(() => admin.listLoginAttempts(LOGIN_LIMIT), [])
  const { data, error } = useLoad<LoginAttempt[]>(load, [])
  return (
    <Section title={`Sign-in attempts (last ${LOGIN_LIMIT}, kept 30 days)`}>
      {error && <p className="error">{error}</p>}
      <Table
        head={['When', 'E-mail', 'IP', 'Outcome']}
        rows={data.map((a) => [
          formatTime(a.at),
          a.email,
          a.ip,
          <span key="outcome" className={`badge ${a.outcome === 'allowed' ? 'ready' : 'failed'}`}>
            {a.outcome}
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
    <Section title={`Visits, last ${VISIT_DAYS} days (per day and path, no addresses)`}>
      {error && <p className="error">{error}</p>}
      <Table head={['Day', 'Path', 'Visits', 'Unique']} rows={data.map((v) => [v.day, v.path, v.visits, v.unique])} />
    </Section>
  )
}

/** Numbers from the three services side by side. Each group loads on its
 *  own, so one service that is down shows its error and the rest stays. */
function Overview() {
  return (
    <Section title="Overview">
      <StatGroup title="Accounts" load={admin.accountStats} tiles={accountTiles} />
      <StatGroup title="Sources" load={admin.ingestStats} tiles={ingestTiles} />
      <StatGroup title="Notebooks and documents" load={admin.ragStats} tiles={ragTiles} />
    </Section>
  )
}

function StatGroup<T>({ title, load, tiles }: { title: string; load: () => Promise<T>; tiles: (s: T) => StatTile[] }) {
  const { data, busy, error } = useLoad<T | null>(load, null)
  return (
    <div className="stat-group">
      <h3>{title}</h3>
      {error && <p className="error">{error}</p>}
      {!data && !error && busy && <p className="muted small">Loading…</p>}
      {data && (
        <div className="stat-grid">
          {tiles(data).map((t) => (
            <div key={t.label} className={t.alert ? 'stat alert' : 'stat'}>
              <span className="stat-value">{t.value}</span>
              <span className="stat-label">{t.label}</span>
              {t.detail && <span className="muted small">{t.detail}</span>}
            </div>
          ))}
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
      <VoucherList key={listVersion} />
    </Section>
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
    if (!confirm(`Delete the open voucher over ${formatCents(v.amount_cents)}? Its code stops working.`)) return
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
        head={['Amount', 'Created by', 'Created', 'Status', 'Redeemed by', 'Redeemed', '']}
        rows={data.map((v) => [
          formatCents(v.amount_cents),
          v.created_by,
          formatTime(v.created_at),
          <span key="status" className={`badge ${v.status === 'open' ? 'ready' : ''}`}>
            {v.status}
          </span>,
          v.redeemed_by ?? '—',
          v.redeemed_at ? formatTime(v.redeemed_at) : '—',
          v.status === 'open' ? (
            <button key="delete" type="button" className="link danger" disabled={busy} onClick={() => void remove(v)}>
              delete
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
    <Section title="Allowed sign-in">
      <p className="muted small">
        Listed addresses, addresses at a listed domain and the configured admins may sign in.
        {empty && ' Both lists are empty: no one but the configured admins can sign in.'}
      </p>
      {error && <p className="error">{error}</p>}
      <div className="grid2">
        <AllowList kind="domain" title="Domains" placeholder="example.org" values={data.allowed_domains} onChange={setData} />
        <AllowList
          kind="address"
          title="Single addresses"
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
    if (!confirm(`Remove ${v} from the allowed ${kind === 'domain' ? 'domains' : 'addresses'}?`)) return
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
            <button type="button" className="icon" title={`Remove ${v}`} disabled={busy} onClick={() => void remove(v)}>
              ×
            </button>
          </li>
        ))}
        {values.length === 0 && <li className="muted small">None.</li>}
      </ul>
      <form className="row" onSubmit={add}>
        <input
          type={kind === 'address' ? 'email' : 'text'}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          aria-label={`Add to ${title.toLowerCase()}`}
          spellCheck={false}
        />
        <button type="submit" disabled={busy || !value.trim()}>
          Add
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
    <Section title="SMTP (sign-in mails)">
      <p className="muted small">Configured in the deployment (Secret lasteverlm-smtp, set by the operator); changing it needs a redeploy.</p>
      {data && configured ? (
        <dl className="kv">
          <dt>Host</dt>
          <dd>{data.host}</dd>
          <dt>Port</dt>
          <dd>{data.port}</dd>
          <dt>Username</dt>
          <dd>{data.username || '—'}</dd>
          <dt>From address</dt>
          <dd>{data.from_address}</dd>
          <dt>STARTTLS</dt>
          <dd>{data.starttls ? 'yes' : 'no'}</dd>
        </dl>
      ) : (
        data && <p>Not configured: sign-in mails cannot be sent.</p>
      )}
      {(loadError ?? error) && <p className="error">{loadError ?? error}</p>}
      {sentTo && <p className="muted">Test mail queued for {sentTo}.</p>}
      <div className="row">
        <button type="button" className="secondary" disabled={busy || !configured} onClick={() => void test()}>
          Send test mail
        </button>
      </div>
    </Section>
  )
}

const RULE_FIELDS: { key: keyof RateLimitUpdate; label: string }[] = [
  { key: 'per_minute', label: 'Requests per minute' },
  { key: 'block_minutes', label: 'Block, minutes' },
  { key: 'ban_after_strikes', label: 'Strikes to a ban' },
  { key: 'strike_window_hours', label: 'Strike window, hours' },
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
    if (!confirm('Reset the rate limit to the deployment defaults?')) return
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
    <Section title="Rate limit and bans">
      <p className="muted small">
        A coarse per-IP limit at the ingress (requests per second, open connections) sits in front of this rule.
      </p>
      {loadError && <p className="error">{loadError}</p>}
      {data && (
        <>
          <p>{describeRateLimit(data)}</p>
          <p className="muted small">
            From the deployment, not editable here: a ban holds at most {data.ban_max_days} days; the access log, stale
            blocks and lifted bans are kept {data.retention_days} days.
          </p>
        </>
      )}
      {values && (
        <form className="grid2" onSubmit={save}>
          {RULE_FIELDS.map((f) => (
            <label key={f.key}>
              {f.label}
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
              Reset to defaults
            </button>
            <button type="submit" disabled={busy || form === null}>
              Save rule
            </button>
          </div>
          <p className="muted small">Every service applies a change within 30 seconds.</p>
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
