import { useEffect, useState } from 'react'
import { ingest } from '../api/ingest'
import { rag } from '../api/rag'
import type { AudioContent, Output } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { formatTime } from '../lib/format'
import { outputOrigin, purgeIn } from '../lib/library'
import { formFor } from '../lib/outputs'
import { OutputContent } from './outputs/OutputContent'
import { t, tn } from '../i18n'

/** The library's Outputs tab: every generated document of the user, newest
 *  first, with the notebook it was made in. "Open" goes to that notebook
 *  with the document selected, or, when the notebook is deleted, shows it
 *  read-only here (the share page's renderer, without sharing). Delete
 *  moves to the trash, one by one with progress, like the sources. */
export function OutputsList({ onOpenNotebook }: { onOpenNotebook: (id: string, outputId: string) => void }) {
  const [outputs, setOutputs] = useState<Output[]>([])
  const [titles, setTitles] = useState<Map<string, string>>(new Map())
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [reading, setReading] = useState<Output | null>(null)
  const { busy, error, run } = useAsync()

  useEffect(() => {
    void run(async () => {
      const [list, notebooks] = await Promise.all([rag.libraryOutputs(), ingest.listNotebooks()])
      setOutputs(list)
      setTitles(new Map(notebooks.map((n) => [n.id, n.title])))
    })
  }, [run])

  const selected = outputs.filter((o) => picked.has(o.id))

  async function open(o: Output) {
    if (o.notebook_id !== null) {
      onOpenNotebook(o.notebook_id, o.id)
      return
    }
    const full = await run(() => rag.getOutput(o.id))
    if (full) setReading(full)
  }

  async function trash(list: Output[]) {
    if (list.length === 0 || !confirm(tn('lib.out.trashConfirm', list.length))) return
    await run(async () => {
      let done = 0
      setProgress({ done, total: list.length })
      try {
        for (const o of list) {
          await rag.deleteOutput(o.id)
          done += 1
          setProgress({ done, total: list.length })
          setOutputs((prev) => prev.filter((x) => x.id !== o.id))
          setPicked((prev) => {
            const next = new Set(prev)
            next.delete(o.id)
            return next
          })
        }
      } finally {
        setProgress(null)
      }
    })
  }

  if (reading) return <ReadOnlyOutput output={reading} onBack={() => setReading(null)} />

  return (
    <>
      <p className="muted small">{t('lib.out.intro')}</p>
      {error && <p className="error">{error}</p>}
      {selected.length > 0 && (
        <div className="selection-bar" role="region" aria-label={tn('lib.selected', selected.length)}>
          <span className="muted small">{progress ? t('lib.progressDelete', progress) : tn('lib.selected', selected.length)}</span>
          <button type="button" className="danger" disabled={busy} onClick={() => void trash(selected)}>
            {tn('lib.deleteN', selected.length)}
          </button>
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th className="pick-col">
              <span className="pick-all">
                <button type="button" className="link small" disabled={outputs.length === 0 || outputs.every((o) => picked.has(o.id))} onClick={() => setPicked(new Set(outputs.map((o) => o.id)))}>
                  {t('lib.selectAll')}
                </button>
                /
                <button type="button" className="link small" disabled={picked.size === 0} onClick={() => setPicked(new Set())}>
                  {t('lib.selectNone')}
                </button>
              </span>
            </th>
            <th>{t('lib.out.title')}</th>
            <th>{t('lib.kind')}</th>
            <th>{t('lib.out.from')}</th>
            <th>{t('lib.out.created')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {outputs.map((o) => {
            const title = o.title || formFor(o.kind).label
            return (
              <tr key={o.id} className={picked.has(o.id) ? 'picked' : undefined}>
                <td className="pick-col">
                  <input
                    type="checkbox"
                    checked={picked.has(o.id)}
                    aria-label={t('lib.selectRow', { name: title })}
                    onChange={() =>
                      setPicked((prev) => {
                        const next = new Set(prev)
                        if (next.has(o.id)) next.delete(o.id)
                        else next.add(o.id)
                        return next
                      })
                    }
                  />
                </td>
                <td className="name">{title}</td>
                <td>
                  {formFor(o.kind).label}
                  {o.status !== 'ready' && <span className={`badge ${o.status}`}> {t(`status.${o.status}`)}</span>}
                </td>
                <td className={o.notebook_id === null ? 'muted' : undefined}>{outputOrigin(o, o.notebook_id ? titles.get(o.notebook_id) : undefined)}</td>
                <td>{formatTime(o.created_at)}</td>
                <td className="row-actions">
                  <button
                    type="button"
                    className="link"
                    disabled={busy}
                    title={o.notebook_id === null ? t('lib.out.openReadOnly', { title }) : t('lib.out.openTitle', { title })}
                    onClick={() => void open(o)}
                  >
                    {t('lib.open')}
                  </button>
                  <button type="button" className="link danger" disabled={busy} onClick={() => void trash([o])}>
                    {t('common.delete')}
                  </button>
                </td>
              </tr>
            )
          })}
          {outputs.length === 0 && !busy && (
            <tr>
              <td className="muted" colSpan={6}>
                {t('lib.out.empty')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  )
}

/** A document whose notebook is gone, as the share page shows one: no
 *  chat, no sharing, print where the kind allows it. */
function ReadOnlyOutput({ output, onBack }: { output: Output; onBack: () => void }) {
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
