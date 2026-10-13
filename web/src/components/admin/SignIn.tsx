import { useState, type FormEvent } from 'react'
import { admin } from '../../api/admin'
import type { AllowKind, Allowlist } from '../../api/types'
import { useAsync } from '../../hooks/useAsync'
import { t } from '../../i18n'
import { Section } from './shared'
import { useLoad } from '../../hooks/useLoad'

const EMPTY_ALLOWLIST: Allowlist = { allowed_domains: [], allowed_addresses: [] }

/** Two lists edited one entry at a time; every change answers with both
 *  lists as stored (normalized, sorted), which replaces the local copy. */
export function AllowedSignIn() {
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
