import { useState, type FormEvent } from 'react'
import { admin } from '../../api/admin'
import type { AdminOutputMatch, AdminOutputSearch } from '../../api/types'
import { useAsync } from '../../hooks/useAsync'
import { formatTime } from '../../lib/format'
import { idPrefix } from '../../lib/idPrefix'
import { formFor } from '../../lib/outputs'
import { t } from '../../i18n'
import { OutputId } from '../OutputId'
import { Section, Table } from './shared'

/** Finds an output by the ID a user quoted ("ID 3f9c21ab"): at least 6 hex
 *  characters, hyphens and case ignored. Each match shows the output, its
 *  owner (the e-mail masked for viewers by rag), its status and every
 *  failed attempt. */
export function OutputSearch() {
  const [input, setInput] = useState('')
  const [result, setResult] = useState<AdminOutputSearch | null>(null)
  const { busy, error, run } = useAsync()
  const prefix = idPrefix(input)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!prefix) return
    const found = await run(() => admin.findOutputs(prefix))
    if (found) setResult(found)
  }

  return (
    <Section title={t('adm.out.title')}>
      <form className="row" onSubmit={submit}>
        <input value={input} placeholder="3f9c21ab" aria-label={t('adm.out.input')} aria-describedby="output-search-hint" onChange={(e) => setInput(e.target.value)} />
        <button type="submit" className="secondary" disabled={busy || !prefix}>
          {t('adm.out.search')}
        </button>
      </form>
      <p id="output-search-hint" className="muted small">
        {t('adm.out.hint')}
      </p>
      {error && <p className="error">{error}</p>}
      {result && result.matches.length === 0 && <p className="muted">{t('adm.out.none')}</p>}
      {result?.matches.map((m) => (
        <Match key={m.id} m={m} />
      ))}
      {result?.truncated && <p className="muted small">{t('adm.out.truncated')}</p>}
    </Section>
  )
}

// core's failure kinds; one this build does not know is shown as sent
const KINDS = new Set(['provider_refused', 'provider', 'configuration', 'timeout', 'internal'])

function Match({ m }: { m: AdminOutputMatch }) {
  return (
    <div className="output-match">
      <p>
        <strong>{m.title || formFor(m.kind).label}</strong> <span className="badge">{formFor(m.kind).label}</span>{' '}
        <span className={`badge ${m.status}`}>{t(`status.${m.status}`)}</span>
        {m.deleted_at && <span className="badge">{t('adm.out.trashed', { when: formatTime(m.deleted_at) })}</span>}
      </p>
      <dl className="kv">
        <dt>{t('outputId.label')}</dt>
        <dd>
          <OutputId id={m.id} full />
        </dd>
        <dt>{t('adm.out.owner')}</dt>
        <dd>
          {m.owner.email} <span className="muted small">({m.owner.id})</span>
        </dd>
        <dt>{t('adm.out.notebook')}</dt>
        <dd>{m.notebook_id ? m.notebook_title : t('adm.out.notebookGone', { title: m.notebook_title })}</dd>
        <dt>{t('adm.out.created')}</dt>
        <dd>{formatTime(m.created_at)}</dd>
        <dt>{t('adm.out.finished')}</dt>
        <dd>{m.finished_at ? formatTime(m.finished_at) : '–'}</dd>
        <dt>{t('adm.out.attempts')}</dt>
        <dd>{m.attempts}</dd>
        {m.error && (
          <>
            <dt>{t('adm.out.error')}</dt>
            <dd className="error">{m.error}</dd>
          </>
        )}
      </dl>
      {m.attempt_log.length > 0 && (
        <Table
          head={[t('adm.out.col.attempt'), t('adm.out.col.at'), t('adm.out.col.service'), t('adm.out.col.model'), t('adm.out.col.kind'), t('adm.out.col.status'), t('adm.out.col.message')]}
          rows={m.attempt_log.map((a) => [
            a.attempt,
            formatTime(a.at),
            a.service,
            a.model ?? '–',
            KINDS.has(a.error_kind) ? t(`adm.out.kind.${a.error_kind}`) : a.error_kind,
            a.provider_status ?? '–',
            a.message,
          ])}
        />
      )}
    </div>
  )
}
