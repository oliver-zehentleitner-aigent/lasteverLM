import { useCallback, useState, type FormEvent } from 'react'
import { admin } from '../../api/admin'
import type { AccessEntry, Ban, Block, RateLimitRules, RateLimitUpdate } from '../../api/types'
import { useAsync } from '../../hooks/useAsync'
import { formatTime } from '../../lib/format'
import { RATE_LIMIT_BOUNDS, describeRateLimit, rateLimitError } from '../../lib/ratelimit'
import { t } from '../../i18n'
import { Section, Table } from './shared'
import { useLoad } from '../../hooks/useLoad'

const ACCESS_LIMIT = 100

const RULE_FIELDS: { key: keyof RateLimitUpdate; label: () => string }[] = [
  { key: 'per_minute', label: () => t('adm.rl.perMinute') },
  { key: 'block_minutes', label: () => t('adm.rl.blockMinutes') },
  { key: 'ban_after_strikes', label: () => t('adm.rl.strikes') },
  { key: 'strike_window_hours', label: () => t('adm.rl.window') },
]

/** The rule behind the blocks and bans below, as a sentence and as the
 *  four numbers an admin may change; every service picks a change up
 *  within 30 seconds. The ban cap and the retention are environment only. */
export function RateLimit() {
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

export function Blocks() {
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

export function Bans() {
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

export function Access() {
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
