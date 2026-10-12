import { useState, type FormEvent } from 'react'
import { account } from '../api/account'
import type { User } from '../api/types'
import { useAsync } from '../hooks/useAsync'

interface Props {
  open: boolean
  reason: 'manual' | 'exhausted'
  onClose: () => void
  onRedeemed: (me: User) => void
}

export function VoucherDialog({ open, reason, onClose, onRedeemed }: Props) {
  const [code, setCode] = useState('')
  const { busy, error, run } = useAsync()

  if (!open) return null

  async function submit(e: FormEvent) {
    e.preventDefault()
    const me = await run(() => account.redeemVoucher(code.trim()))
    if (me) {
      setCode('')
      onRedeemed(me)
    }
  }

  return (
    <div className="backdrop" onClick={onClose}>
      <form className="dialog" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2>Redeem a voucher</h2>
        {reason === 'exhausted' && <p className="error">Your credit is used up. Enter a voucher code to continue.</p>}
        <label>
          Code
          <input autoFocus value={code} onChange={(e) => setCode(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <div className="row">
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
          <button type="submit" disabled={busy || !code.trim()}>
            {busy ? 'Redeeming…' : 'Redeem'}
          </button>
        </div>
      </form>
    </div>
  )
}
