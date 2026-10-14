import { useEffect, useState } from 'react'
import { rag } from '../api/rag'
import type { AudioContent, Output } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { formatTime } from '../lib/format'
import { purgeIn } from '../lib/library'
import { formFor } from '../lib/outputs'
import { OutputContent } from './outputs/OutputContent'
import { t } from '../i18n'

/** A document whose notebook is gone, as the share page shows one: no
 *  chat, no sharing, print where the kind allows it. */
export function ReadOnlyOutput({ output, onBack }: { output: Output; onBack: () => void }) {
  const form = formFor(output.kind)
  return (
    <section className="read-only-output">
      <p>
        <button type="button" className="link" onClick={onBack}>
          ← {t('lib.out.back')}
        </button>
      </p>
      <p className="muted small">{t('lib.out.readOnly')}</p>
      <div className="viewer-body printable">
        <header className="viewer-head">
          <h1 className="doc-title">{output.title || form.label}</h1>
          <span className="badge">{form.label}</span>
          <span className="muted small">{formatTime(output.created_at)}</span>
          {form.printable && output.status === 'ready' && (
            <span className="actions no-print">
              <button type="button" className="link" onClick={() => window.print()}>
                {t('viewer.print')}
              </button>
            </span>
          )}
        </header>
        <OutputContent
          kind={output.kind}
          title={output.title}
          status={output.status}
          error={output.error}
          content={output.content}
          onExpired={() => rag.getOutput(output.id).then((o) => (o.content as AudioContent).url)}
        />
      </div>
    </section>
  )
}

/** The trashed documents, under the trashed sources: restore (into the
 *  notebook it was made in, when that still exists) or delete for good. */
export function TrashedOutputs() {
  const [outputs, setOutputs] = useState<Output[]>([])
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => setOutputs(await rag.libraryOutputs(true)))
  }, [run])

  async function restore(o: Output) {
    if (await run(() => rag.restoreOutput(o.id).then(() => true))) setOutputs((prev) => prev.filter((x) => x.id !== o.id))
  }

  async function purge(o: Output) {
    if (!confirm(t('lib.out.purgeConfirm', { title: o.title || formFor(o.kind).label }))) return
    if (await run(() => rag.purgeOutput(o.id).then(() => true))) setOutputs((prev) => prev.filter((x) => x.id !== o.id))
  }

  return (
    <>
      <h2>{t('lib.out.trashed')}</h2>
      <p className="muted small">{t('lib.out.restoreNote')}</p>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>{t('lib.out.title')}</th>
            <th>{t('lib.kind')}</th>
            <th>{t('lib.out.from')}</th>
            <th>{t('lib.deleted')}</th>
            <th>{t('lib.purge')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {outputs.map((o) => (
            <tr key={o.id}>
              <td className="name">{o.title || formFor(o.kind).label}</td>
              <td>{formFor(o.kind).label}</td>
              <td className="muted">{o.origin_title ?? ''}</td>
              <td>{o.deleted_at ? formatTime(o.deleted_at) : ''}</td>
              <td title={o.purge_at ? formatTime(o.purge_at) : undefined}>{o.purge_at ? purgeIn(o.purge_at) : ''}</td>
              <td className="actions-cell">
                <button type="button" className="link" disabled={busy} onClick={() => void restore(o)}>
                  {t('lib.restore')}
                </button>
                <button type="button" className="link danger" disabled={busy} onClick={() => void purge(o)}>
                  {t('lib.deleteForGood')}
                </button>
              </td>
            </tr>
          ))}
          {outputs.length === 0 && !busy && (
            <tr>
              <td className="muted" colSpan={6}>
                {t('lib.out.trashEmpty')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  )
}
