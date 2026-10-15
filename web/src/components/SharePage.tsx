import { useEffect, useState, type ReactNode } from 'react'
import { account } from '../api/account'
import { rag } from '../api/rag'
import type { AudioContent, SharedNotebook, SharedOutput } from '../api/types'
import { formatTime } from '../lib/format'
import { optionsLabel, speakerName } from '../lib/outputOptions'
import { formFor, sourceKindLabel } from '../lib/outputs'
import { OutputContent } from './outputs/OutputContent'
import { OutputProvenance } from './OutputProvenance'
import { checkSummary } from '../lib/outputProvenance'
import { judgeHead } from '../lib/judge'
import { t } from '../i18n'

function SharedShell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <main className="shared">
      <header className="topbar no-print">
        <a href="/" className="brand">
          lasteverLM
        </a>
        <span className="muted small">{label}</span>
      </header>
      <div className="viewer-body printable">{children}</div>
    </main>
  )
}

/** One shared output as a reader sees it: its head (title, kind, date,
 *  what it was made with, the check) and its content with the passages and
 *  the log, nothing to open. Used by the output's and the notebook's
 *  share page. `refresh` re-reads it for a fresh audio url. */
function SharedOutputView({ doc, refresh, level = 1 }: { doc: SharedOutput; refresh: () => Promise<SharedOutput>; level?: 1 | 2 }) {
  const Title = level === 1 ? 'h1' : 'h2'
  return (
    <>
      <header className="viewer-head">
        <Title className="doc-title">{doc.title || formFor(doc.kind).label}</Title>
        <span className="badge">{formFor(doc.kind).label}</span>
        <span className="muted small">{formatTime(doc.created_at)}</span>
        {/* no spec here: it needs a login, so the codes are shown as they are */}
        {optionsLabel(doc.options, null) && <span className="muted small">{optionsLabel(doc.options, null)}</span>}
        {checkSummary(doc.provenance?.check, doc.kind) && <span className="muted small check-line">{checkSummary(doc.provenance?.check, doc.kind)}</span>}
        {judgeHead(doc.provenance) && <span className="muted small check-line judge-line">{judgeHead(doc.provenance)}</span>}
        {level === 1 && formFor(doc.kind).printable && (
          <span className="actions no-print">
            <button type="button" className="link" onClick={() => window.print()}>
              {t('viewer.print')}
            </button>
          </span>
        )}
      </header>
      {/* the author's instructions travel with a shared output, so a reader sees what was asked for */}
      {doc.options?.instructions && (
        <p className="muted small author-instructions">
          {t('opt.authorInstructions')}: {doc.options.instructions}
        </p>
      )}
      {/* read-only: the passages and the log, no source to open */}
      <OutputProvenance output={doc} provenance={doc.provenance}>
        <OutputContent
          kind={doc.kind}
          title={doc.title}
          status="ready"
          error={null}
          content={doc.content}
          onExpired={() => refresh().then((d) => (d.content as AudioContent).url)}
          speakerName={(s) => speakerName(s, doc.options, null)}
        />
      </OutputProvenance>
    </>
  )
}

/** /s/<token>: one generated document, read-only, no login. The page view
 *  goes to the visitor log like any other. */
export function SharePage({ token }: { token: string }) {
  const [doc, setDoc] = useState<SharedOutput | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    account.recordVisit('/s/').catch(() => {})
    rag.getShared(token).then(setDoc, (e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [token])

  return (
    <SharedShell label={t('share.shared')}>
      {error && <p className="error">{error}</p>}
      {!doc && !error && <p className="muted">{t('common.loading')}</p>}
      {doc && <SharedOutputView doc={doc} refresh={() => rag.getShared(token)} />}
    </SharedShell>
  )
}

/** /shared/notebook/<token>: a notebook, read-only, no login: its title,
 *  its sources by name and kind (no files), and its outputs one after the
 *  other, oldest first, each as on its own share page, with a list of
 *  them at the top to jump to. */
export function SharedNotebookPage({ token }: { token: string }) {
  const [nb, setNb] = useState<SharedNotebook | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    account.recordVisit('/shared/notebook/').catch(() => {})
    rag.getSharedNotebook(token).then(setNb, (e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [token])

  return (
    <SharedShell label={t('nbShare.shared')}>
      {error && <p className="error">{error}</p>}
      {!nb && !error && <p className="muted">{t('common.loading')}</p>}
      {nb && (
        <div className="shared-notebook">
          <h1 className="doc-title">{nb.title}</h1>
          <section className="shared-sources">
            <h2>{t('nbShare.sources', { n: nb.sources.length })}</h2>
            <ul>
              {nb.sources.map((s, i) => (
                <li key={i}>
                  <span className="badge">{sourceKindLabel(s.kind)}</span> {s.name}
                </li>
              ))}
            </ul>
          </section>
          {nb.outputs.length === 0 ? (
            <p className="muted">{t('nbShare.noOutputs')}</p>
          ) : (
            <>
              <nav className="shared-toc no-print" aria-label={t('nbShare.outputs')}>
                <h2>{t('nbShare.outputs')}</h2>
                <ol>
                  {nb.outputs.map((o, i) => (
                    <li key={i}>
                      <a href={`#output-${i + 1}`}>{o.title || formFor(o.kind).label}</a> <span className="muted small">{formFor(o.kind).label}</span>
                    </li>
                  ))}
                </ol>
              </nav>
              {nb.outputs.map((o, i) => (
                <article key={i} id={`output-${i + 1}`} className="shared-output">
                  <SharedOutputView doc={o} level={2} refresh={() => rag.getSharedNotebook(token).then((n) => n.outputs[i] ?? o)} />
                </article>
              ))}
            </>
          )}
        </div>
      )}
    </SharedShell>
  )
}
