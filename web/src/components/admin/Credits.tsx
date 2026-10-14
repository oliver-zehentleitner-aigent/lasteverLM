import { useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { admin } from '../../api/admin'
import type { Voucher, VoucherSend } from '../../api/types'
import { CopyButton } from '../CopyButton'
import { useAsync } from '../../hooks/useAsync'
import { formatCents, formatTime } from '../../lib/format'
import { t } from '../../i18n'
import { useCanWrite } from './canWrite'
import { Section, Table } from './shared'
import { useLoad } from '../../hooks/useLoad'
import { MESSAGE_MAX, plausibleEmail, voucherError } from '../../lib/vouchers'

const VOUCHER_LIMIT = 100

export function Vouchers() {
  const [amount, setAmount] = useState('5.00')
  const [count, setCount] = useState('1')
  const [codes, setCodes] = useState<string[]>([])
  const [listVersion, setListVersion] = useState(0)
  // optionally mailed right away, each created voucher to the same address
  const [sendOn, setSendOn] = useState(false)
  const [paid, setPaid] = useState(false)
  const [send, setSend] = useState<VoucherSend>({ email: '', message: '', allow: true })
  const [sentTo, setSentTo] = useState<string | null>(null)
  const sendBad = sendOn && !plausibleEmail(send.email)
  const { busy, error, run } = useAsync()
  const canWrite = useCanWrite()

  async function create(e: FormEvent) {
    e.preventDefault()
    const cents = Math.round(Number(amount.replace(',', '.')) * 100)
    const n = Number(count)
    if (!Number.isFinite(cents) || cents <= 0 || !Number.isInteger(n) || n <= 0 || sendBad) return
    setSentTo(null)
    const target = sendOn ? cleanSend(send) : undefined
    const created = await run(async () => {
      try {
        return await admin.createVouchers(cents, n, target, paid)
      } catch (err) {
        throw new Error(voucherError(err))
      }
    })
    if (created) {
      setCodes(created)
      setListVersion((v) => v + 1)
      if (target) setSentTo(target.email)
    }
  }

  return (
    <Section title={t('adm.vouchers')}>
      <div className="voucher-create">
        <form className="row" onSubmit={create}>
          <fieldset className="plain row" disabled={!canWrite} title={canWrite ? undefined : t('adm.readOnlyTitle')}>
          <label>
            {t('adm.amountEur')}
            <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </label>
          <label>
            {t('adm.count')}
            <input type="number" min={1} max={100} value={count} onChange={(e) => setCount(e.target.value)} />
          </label>
          <label className="check" title={t('vch.paidTitle')}>
            <input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} /> {t('vch.paid')}
          </label>
          <button type="submit" disabled={busy || sendBad}>
            {t('adm.create')}
          </button>
          </fieldset>
          {canWrite && (
            <div className="voucher-send-block">
              <label className="check">
                <input type="checkbox" checked={sendOn} onChange={(e) => setSendOn(e.target.checked)} /> {t('vch.sendTo')}
              </label>
              {sendOn && <SendFields value={send} onChange={setSend} />}
            </div>
          )}
        </form>
        {sentTo && <p className="muted small">{t('vch.sentCreated', { to: sentTo })}</p>}
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
  const canWrite = useCanWrite()
  const [sending, setSending] = useState<Voucher | null>(null)

  /** paid or free: for the revenue page, changeable after the fact */
  async function markPaid(v: Voucher, paid: boolean) {
    const updated = await run(() => admin.setVoucherPaid(v.id, paid))
    if (updated) setData((list) => list.map((x) => (x.id === updated.id ? updated : x)))
  }

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
          t('vch.code'),
          t('adm.col.amount'),
          t('adm.col.createdBy'),
          t('adm.col.created'),
          t('adm.col.status'),
          t('vch.paidCol'),
          t('adm.col.redeemedBy'),
          t('adm.col.redeemed'),
          '',
        ]}
        rows={data.map((v) => [
          <CodeCell key="code" voucher={v} canShow={canWrite} />,
          formatCents(v.amount_cents),
          v.created_by,
          formatTime(v.created_at),
          <span key="status">
            <span className={`badge ${v.status === 'open' ? 'ready' : ''}`}>{t(`status.${v.status}`)}</span>
            {v.sent_to && (
              <span className="muted small sent">
                {' '}
                {t('vch.sentTo', { to: v.sent_to, at: formatTime(v.sent_at ?? null) })}
              </span>
            )}
          </span>,
          <label key="paid" className="check small" title={t('vch.paidTitle')}>
            <input type="checkbox" checked={v.paid ?? false} disabled={busy || !canWrite} aria-label={t('vch.paid')} onChange={(e) => void markPaid(v, e.target.checked)} />{' '}
            {v.paid ? t('vch.paid') : t('vch.free')}
          </label>,
          v.redeemed_by ?? '—',
          v.redeemed_at ? formatTime(v.redeemed_at) : '—',
          v.status === 'open' ? (
            <span key="actions" className="row-actions">
              {canWrite && v.recoverable !== false && (
                <button type="button" className="link" disabled={busy} onClick={() => setSending(v)}>
                  {t('vch.send')}
                </button>
              )}
              <button type="button" className="link danger" disabled={busy || !canWrite} title={canWrite ? undefined : t('adm.readOnlyTitle')} onClick={() => void remove(v)}>
                {t('common.delete')}
              </button>
            </span>
          ) : (
            ''
          ),
        ])}
      />
      {sending && (
        <SendDialog
          voucher={sending}
          onClose={() => setSending(null)}
          onSent={(updated) => {
            setSending(null)
            setData((list) => list.map((x) => (x.id === updated.id ? updated : x)))
          }}
        />
      )}
    </>
  )
}

const cleanSend = (s: VoucherSend): VoucherSend => ({ email: s.email.trim(), message: s.message?.trim() || undefined, allow: s.allow ?? true })

/** Recipient, an optional note and "also allow to sign in", for the send
 *  dialog and the create form alike. */
function SendFields({ value, onChange }: { value: VoucherSend; onChange: (v: VoucherSend) => void }) {
  const message = value.message ?? ''
  return (
    <div className="send-fields">
      <label>
        {t('vch.email')}
        <input type="email" autoComplete="off" value={value.email} onChange={(e) => onChange({ ...value, email: e.target.value })} />
      </label>
      <label>
        {t('vch.message')}
        <textarea rows={3} maxLength={MESSAGE_MAX} value={message} onChange={(e) => onChange({ ...value, message: e.target.value })} />
        <span className="muted small">{t('vch.messageHint', { n: message.length, max: MESSAGE_MAX })}</span>
      </label>
      <label className="check">
        <input type="checkbox" checked={value.allow ?? true} onChange={(e) => onChange({ ...value, allow: e.target.checked })} /> {t('vch.allow')}
      </label>
    </div>
  )
}

/** Mails one voucher's code; a refusal (quota, no mail server, the mail
 *  server's error, already redeemed) stays in the dialog. */
function SendDialog({ voucher, onClose, onSent }: { voucher: Voucher; onClose: () => void; onSent: (v: Voucher) => void }) {
  const [value, setValue] = useState<VoucherSend>({ email: '', message: '', allow: true })
  const { busy, error, run } = useAsync()
  const ok = plausibleEmail(value.email)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!ok) return
    const updated = await run(async () => {
      try {
        return await admin.sendVoucher(voucher.id, cleanSend(value))
      } catch (err) {
        throw new Error(voucherError(err))
      }
    })
    if (updated) onSent(updated)
  }

  return (
    <div className="backdrop" onClick={busy ? undefined : onClose}>
      <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="send-voucher-title" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 id="send-voucher-title">{t('vch.sendTitle', { amount: formatCents(voucher.amount_cents) })}</h2>
        <SendFields value={value} onChange={setValue} />
        {value.email && !ok && <p className="muted small">{t('vch.badEmail')}</p>}
        {error && <p className="error">{error}</p>}
        <div className="row">
          <button type="button" className="secondary" disabled={busy} onClick={onClose}>
            {t('common.close')}
          </button>
          <button type="submit" disabled={busy || !ok}>
            {busy ? t('vch.sending') : t('vch.sendNow')}
          </button>
        </div>
      </form>
    </div>
  )
}

/** The code as kept: masked, and for an admin "show" to fetch it once
 *  with a copy button next to it; a voucher from before codes were kept
 *  says so instead. */
function CodeCell({ voucher: v, canShow }: { voucher: Voucher; canShow: boolean }) {
  const [code, setCode] = useState<string | null>(null)
  const [gone, setGone] = useState(v.recoverable === false)
  const [error, setError] = useState<string | null>(null)
  const el = useRef<HTMLElement>(null)

  async function show() {
    setError(null)
    try {
      setCode(await admin.voucherCode(v.id))
    } catch (err) {
      if (err instanceof ApiError && err.code === 'not_recoverable') setGone(true)
      else setError(voucherError(err))
    }
  }

  if (gone) return <span className="muted small">{t('vch.notRecoverable')}</span>
  return (
    <span className="code-cell">
      <code ref={el}>{code ?? v.code_masked ?? '—'}</code>
      {canShow &&
        (code ? (
          <>
            <CopyButton text={code} target={el} />
            <button type="button" className="link small" onClick={() => setCode(null)}>
              {t('vch.hide')}
            </button>
          </>
        ) : (
          <button type="button" className="link small" onClick={() => void show()}>
            {t('vch.show')}
          </button>
        ))}
      {error && <span className="error small"> {error}</span>}
    </span>
  )
}
