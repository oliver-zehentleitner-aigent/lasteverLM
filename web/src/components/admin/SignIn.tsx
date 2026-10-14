import { useState, type FormEvent } from 'react'
import { admin } from '../../api/admin'
import type { AllowKind, Allowlist } from '../../api/types'
import { useAsync } from '../../hooks/useAsync'
import { t } from '../../i18n'
import { useCanWrite } from './canWrite'
import { Section } from './shared'
import { useLoad } from '../../hooks/useLoad'

const EMPTY_ALLOWLIST: Allowlist = { allowed_domains: [], allowed_addresses: [], viewer_domains: [], viewer_addresses: [] }

/** Who gets in, in two blocks that read the same way: sign-in, then the
 *  viewers (the admin panel, read-only), each a heading, its line, and
 *  Domains | Single addresses side by side, stacked on a phone. Lists are
 *  edited one entry at a time; every change answers with all lists as
 *  stored (normalized, sorted), which replaces the local copy. */
export function AllowedSignIn() {
  const { data, setData, error } = useLoad<Allowlist>(admin.getAllowlist, EMPTY_ALLOWLIST)
  const empty = data.allowed_domains.length === 0 && data.allowed_addresses.length === 0
  return (
    <Section title={t('adm.accessTitle')}>
      {error && <p className="error">{error}</p>}
      <section className="access-block">
        <h3>{t('adm.signInBlock')}</h3>
        <p className="muted small">
          {t('adm.allowedHint')}
          {empty && t('adm.allowedEmpty')}
        </p>
        <div className="grid2">
          <AllowList kind="domain" title={t('adm.domains')} placeholder="example.org" values={data.allowed_domains} onChange={setData} />
          <AllowList kind="address" title={t('adm.addresses')} placeholder="name@example.org" values={data.allowed_addresses} onChange={setData} />
        </div>
      </section>
      <section className="access-block">
        <h3>{t('adm.viewerBlock')}</h3>
        <p className="muted small">{t('adm.viewerDomainsHint')}</p>
        <div className="grid2">
          <AllowList kind="viewer" title={t('adm.domains')} placeholder="review.example.org" values={data.viewer_domains ?? []} onChange={setData} />
          <AllowList kind="viewer_address" title={t('adm.addresses')} placeholder="reviewer@example.org" values={data.viewer_addresses ?? []} onChange={setData} />
        </div>
      </section>
    </Section>
  )
}

const REMOVE_CONFIRM = {
  domain: 'adm.removeAllowedDomain',
  address: 'adm.removeAllowedAddress',
  viewer: 'adm.removeViewerDomain',
  viewer_address: 'adm.removeViewerAddress',
} as const

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
  const canWrite = useCanWrite()

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
    if (!confirm(t(REMOVE_CONFIRM[kind], { v }))) return
    const ok = await run(async () => {
      await admin.removeAllowed(kind, v)
      return true
    })
    if (ok) onChange(await admin.getAllowlist())
  }

  return (
    <div className="allow-list">
      <h4>{title}</h4>
      <ul className="list">
        {/* a viewer gets addresses masked, and two can mask alike */}
        {values.map((v, i) => (
          <li key={`${i}:${v}`}>
            <span className="item">{v}</span>
            <button type="button" className="icon" title={canWrite ? t('adm.remove', { v }) : t('adm.readOnlyTitle')} disabled={busy || !canWrite} onClick={() => void remove(v)}>
              ×
            </button>
          </li>
        ))}
        {values.length === 0 && <li className="muted small">{t('adm.none')}</li>}
      </ul>
      <form className="row" onSubmit={add}>
        <fieldset className="plain row" disabled={!canWrite} title={canWrite ? undefined : t('adm.readOnlyTitle')}>
        <input
          type={kind === 'address' || kind === 'viewer_address' ? 'email' : 'text'}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          aria-label={t('adm.addTo', { list: title })}
          spellCheck={false}
        />
        <button type="submit" disabled={busy || !value.trim()}>
          {t('common.add')}
        </button>
        </fieldset>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  )
}
