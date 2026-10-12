import { useEffect, useState } from 'react'
import { account } from '../api/account'
import { rag } from '../api/rag'
import type { SharedOutput } from '../api/types'
import { formatTime } from '../lib/format'
import { formFor } from '../lib/outputs'
import { OutputContent } from './outputs/OutputContent'

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
    <main className="shared">
      <header className="topbar no-print">
        <a href="/" className="brand">
          lasteverLM
        </a>
        <span className="muted small">shared document</span>
      </header>
      <div className="viewer-body printable">
        {error && <p className="error">{error}</p>}
        {!doc && !error && <p className="muted">Loading…</p>}
        {doc && (
          <>
            <header className="viewer-head">
              <h1 className="doc-title">{doc.title || formFor(doc.kind).label}</h1>
              <span className="badge">{formFor(doc.kind).label}</span>
              <span className="muted small">{formatTime(doc.created_at)}</span>
              {formFor(doc.kind).printable && (
                <span className="actions no-print">
                  <button type="button" className="link" onClick={() => window.print()}>
                    print
                  </button>
                </span>
              )}
            </header>
            <OutputContent kind={doc.kind} title={doc.title} status="ready" error={null} content={doc.content} />
          </>
        )}
      </div>
    </main>
  )
}
