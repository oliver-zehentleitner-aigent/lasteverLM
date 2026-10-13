import { useRef, useState, type FormEvent } from 'react'
import { admin } from '../../api/admin'
import type { Voucher } from '../../api/types'
import { CopyButton } from '../CopyButton'
import { useAsync } from '../../hooks/useAsync'
import { formatCents, formatTime } from '../../lib/format'
import { t } from '../../i18n'
import { Section, Table } from './shared'
import { useLoad } from '../../hooks/useLoad'

const VOUCHER_LIMIT = 100

export function Vouchers() {
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
