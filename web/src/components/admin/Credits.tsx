import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { admin } from '../../api/admin'
import type { Voucher, VoucherSend } from '../../api/types'
import { CopyButton } from '../CopyButton'
import { useAsync } from '../../hooks/useAsync'
import { formatCents, formatShortTime, formatTime } from '../../lib/format'
import { t } from '../../i18n'
import { useCanWrite } from './canWrite'
import { IconEye, IconMail, IconTrash } from '../Icons'
import { Section } from './shared'
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
      {/* a form card above the list: amount, count and paid in one row; the
          optional mail below it, full width; Create at the bottom right */}
      <form className="card voucher-form" onSubmit={create}>
        <fieldset className="plain voucher-form-fields" disabled={!canWrite} title={canWrite ? undefined : t('adm.readOnlyTitle')}>
          <div className="voucher-form-row">
            <label>
              {t('adm.amountEur')}
              <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </label>
            <label>
              {t('adm.count')}
              <input type="number" min={1} max={100} value={count} onChange={(e) => setCount(e.target.value)} />
            </label>
            <label className="check" title={t('vch.paidTitle')}>
              <input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} />
              {t('vch.paidVoucher')}
            </label>
          </div>
          {canWrite && (
            <label className="check">
              <input type="checkbox" checked={sendOn} onChange={(e) => setSendOn(e.target.checked)} />
              {t('vch.sendTo')}
            </label>
          )}
          {canWrite && sendOn && <SendFields value={send} onChange={setSend} />}
          <div className="voucher-form-actions">
            <button type="submit" disabled={busy || sendBad}>
              {t('adm.create')}
            </button>
          </div>
        </fieldset>
      </form>
      {sentTo && <p className="muted small">{t('vch.sentCreated', { to: sentTo })}</p>}
      {codes.length > 0 && <VoucherCodes codes={codes} />}
      {error && <p className="error">{error}</p>}
      <VoucherList key={listVersion} />
    </Section>
  )
}

/** The codes just created: compact chips with a copy button each, and
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
 *  appear. The codes are listed masked; an admin shows one with the eye.
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

  // a dated cell: compact, the full time in the tooltip
  const when = (iso: string | null) => <span title={iso ? formatTime(iso) : undefined}>{iso ? formatShortTime(iso) : '—'}</span>
  return (
    <>
      {(error ?? actionError) && <p className="error">{error ?? actionError}</p>}
      <table className="voucher-table">
        <thead>
          <tr>
            <th>{t('vch.code')}</th>
            <th>{t('adm.col.amount')}</th>
            <th>{t('adm.col.createdBy')}</th>
            <th>{t('adm.col.created')}</th>
            <th>{t('adm.col.status')}</th>
            <th>{t('adm.col.redeemed')}</th>
            <th>
              <span className="sr-only">{t('vch.actions')}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((v) => {
            const gone = v.recoverable === false
            return (
              <tr key={v.id}>
                <td data-label={t('vch.code')}>
                  {gone ? (
                    <span className="muted small" title={t('vch.notRecoverable')}>
                      {t('vch.notRecoverableShort')}
                    </span>
                  ) : (
                    <code>{v.code_masked ?? '—'}</code>
                  )}
                </td>
                <td data-label={t('adm.col.amount')}>{formatCents(v.amount_cents)}</td>
                <td data-label={t('adm.col.createdBy')}>
                  <span className="clip" title={v.created_by}>
                    {v.created_by}
                  </span>
                </td>
                <td data-label={t('adm.col.created')}>{when(v.created_at)}</td>
                <td data-label={t('adm.col.status')}>
                  <span className="voucher-badges">
                    <span className={`badge ${v.status === 'open' ? 'ready' : ''}`}>{t(`status.${v.status}`)}</span>
                    {canWrite ? (
                      <label className="check small paid-toggle" title={t('vch.paidTitle')}>
                        <input type="checkbox" checked={v.paid ?? false} disabled={busy} onChange={(e) => void markPaid(v, e.target.checked)} />
                        {v.paid ? t('vch.paid') : t('vch.free')}
                      </label>
                    ) : (
                      <span className="badge" title={t('vch.paidTitle')}>
                        {v.paid ? t('vch.paid') : t('vch.free')}
                      </span>
                    )}
                  </span>
                  {v.sent_to && (
                    <span className="muted small clip sent" title={t('vch.sentTo', { to: v.sent_to, at: formatTime(v.sent_at ?? null) })}>
                      {t('vch.sentToShort', { to: v.sent_to })}
                    </span>
                  )}
                </td>
                <td data-label={t('adm.col.redeemed')}>
                  {v.redeemed_by ? (
                    <span className="two-line">
                      <span className="clip" title={v.redeemed_by}>
                        {v.redeemed_by}
                      </span>
                      <span className="muted small">{when(v.redeemed_at)}</span>
                    </span>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="row-actions">
                  {canWrite && !gone && <CodeReveal voucher={v} />}
                  {canWrite && v.status === 'open' && !gone && (
                    <button type="button" className="icon icon-action" disabled={busy} title={t('vch.sendTitleShort')} aria-label={t('vch.sendLabel', { amount: formatCents(v.amount_cents) })} onClick={() => setSending(v)}>
                      <IconMail />
                    </button>
                  )}
                  {v.status === 'open' && (
                    <button
                      type="button"
                      className="icon icon-danger"
                      disabled={busy || !canWrite}
                      title={canWrite ? t('vch.deleteTitle') : t('adm.readOnlyTitle')}
                      aria-label={t('vch.deleteLabel', { amount: formatCents(v.amount_cents) })}
                      onClick={() => void remove(v)}
                    >
                      <IconTrash />
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
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
        <input type="checkbox" checked={value.allow ?? true} onChange={(e) => onChange({ ...value, allow: e.target.checked })} />
        {t('vch.allow')}
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

/** The eye in a voucher's row: fetches the code once and shows it in a
 *  small popover with a copy button; a click elsewhere or Esc closes it
 *  (and the code is not kept). A voucher whose code was not kept says so. */
function CodeReveal({ voucher: v }: { voucher: Voucher }) {
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState<string | null>(null)
  const [gone, setGone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const box = useRef<HTMLSpanElement>(null)
  const el = useRef<HTMLElement>(null)
  const button = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const away = (e: Event) => {
      if (!box.current?.contains(e.target as Node)) close()
    }
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        close()
        button.current?.focus()
      }
    }
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('pointerdown', away)
      document.removeEventListener('keydown', key)
    }
  }, [open])

  function close() {
    setOpen(false)
    setCode(null)
  }

  async function reveal() {
    if (open) return close()
    setOpen(true)
    setError(null)
    try {
      setCode(await admin.voucherCode(v.id))
    } catch (err) {
      if (err instanceof ApiError && err.code === 'not_recoverable') setGone(true)
      else setError(voucherError(err))
    }
  }

  return (
    <span className="code-reveal" ref={box}>
      <button ref={button} type="button" className="icon icon-action" aria-expanded={open} title={t('vch.showTitle')} aria-label={t('vch.showLabel', { amount: formatCents(v.amount_cents) })} onClick={() => void reveal()}>
        <IconEye />
      </button>
      {open && (
        <span className="code-popover" role="dialog" aria-label={t('vch.showTitle')}>
          {gone ? (
            <span className="muted small">{t('vch.notRecoverable')}</span>
          ) : error ? (
            <span className="error small">{error}</span>
          ) : code ? (
            <>
              <code ref={el}>{code}</code>
              <CopyButton text={code} target={el} />
            </>
          ) : (
            <span className="muted small">{t('common.loading')}</span>
          )}
        </span>
      )}
    </span>
  )
}
