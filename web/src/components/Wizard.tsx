import { useState, type DragEvent } from 'react'
import { ingest } from '../api/ingest'
import { rag } from '../api/rag'
import type { OutputKind, SourceKind } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { OUTPUT_FORMS, SOURCE_FORMS, type SourceForm } from '../lib/outputs'

interface Props {
  notebookId: string
  onDone: () => void
  onClose: () => void
}

type Step = 1 | 2 | 3

/** Adding sources in three steps, one question each, tiles instead of a
 *  form. Step 2 uploads per file as soon as the user confirms; step 3
 *  creates one output per selected kind, and rag waits for the sources
 *  itself, so closing the browser after "Done" loses nothing. */
export function Wizard({ notebookId, onDone, onClose }: Props) {
  const [step, setStep] = useState<Step>(1)
  const [form, setForm] = useState<SourceForm | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [pasted, setPasted] = useState('')
  const [url, setUrl] = useState('')
  const [kinds, setKinds] = useState<Set<OutputKind>>(new Set())
  const [uploaded, setUploaded] = useState(0)
  const { busy, error, run } = useAsync()

  const canUpload = form?.input === 'url' ? url.trim() !== '' : files.length > 0 || pasted.trim() !== ''

  async function upload() {
    if (!form) return
    const ok = await run(async () => {
      if (form.input === 'url') {
        await ingest.addUrl(notebookId, url.trim())
        setUploaded(1)
        return true
      }
      let n = 0
      for (const f of files) {
        await ingest.uploadFile(notebookId, f)
        n += 1
        setUploaded(n)
      }
      if (pasted.trim()) {
        const name = `${pasted.trim().split('\n')[0].slice(0, 40) || 'pasted'}.txt`
        await ingest.uploadFile(notebookId, new File([pasted], name, { type: 'text/plain' }))
        setUploaded(n + 1)
      }
      return true
    })
    if (ok) setStep(3)
  }

  async function finish() {
    const ok = await run(async () => {
      for (const k of kinds) await rag.createOutput(notebookId, k)
      return true
    })
    if (ok) onDone()
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    addFiles(e.dataTransfer.files)
  }
  function addFiles(list: FileList | null) {
    if (!list) return
    setFiles((prev) => [...prev, ...Array.from(list)])
  }

  return (
    <div className="backdrop" onClick={onClose}>
      <div className="dialog wizard" onClick={(e) => e.stopPropagation()}>
        <header className="row">
          <span className="muted small">Step {step} of 3</span>
          <button type="button" className="icon" onClick={onClose} title="Close">
            ×
          </button>
        </header>

        {step === 1 && (
          <>
            <h2>What goes in?</h2>
            <div className="tile-grid">
              {SOURCE_FORMS.map((f) => (
                <button
                  key={f.kind}
                  type="button"
                  className="tile"
                  disabled={!f.available}
                  onClick={() => {
                    setForm(f)
                    setStep(2)
                  }}
                >
                  <strong>{f.label}</strong>
                  <span className="muted small">{f.description}</span>
                </button>
              ))}
            </div>
          </>
        )}

        {step === 2 && form && (
          <>
            <h2>How does it get in?</h2>
            {form.input === 'files' && (
              <div
                className="drop"
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDrop}
              >
                <p>Drop {form.label} files here, or</p>
                <input type="file" multiple accept={form.accept} onChange={(e) => addFiles(e.target.files)} />
                {files.length > 0 && (
                  <ul className="list small">
                    {files.map((f, i) => (
                      <li key={i}>
                        <span className="item">{f.name}</span>
                        <button type="button" className="icon" onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}>
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {form.kind === 'text' && (
                  <label>
                    or paste text
                    <textarea rows={5} value={pasted} onChange={(e) => setPasted(e.target.value)} />
                  </label>
                )}
              </div>
            )}
            {form.input === 'url' && (
              <label>
                Address
                <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" autoFocus />
              </label>
            )}
            {busy && <p className="muted">Uploading… {uploaded}</p>}
            {error && <p className="error">{error}</p>}
            <div className="row">
              <button type="button" className="secondary" onClick={() => setStep(1)} disabled={busy}>
                Back
              </button>
              <button type="button" onClick={() => void upload()} disabled={busy || !canUpload}>
                Add
              </button>
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <h2>What should come out of it?</h2>
            <p className="muted small">Pick any number, or none to just chat.</p>
            <div className="tile-grid">
              {OUTPUT_FORMS.map((f) => (
                <button
                  key={f.kind}
                  type="button"
                  className={kinds.has(f.kind) ? 'tile selected' : 'tile'}
                  disabled={!f.available}
                  aria-pressed={kinds.has(f.kind)}
                  onClick={() =>
                    setKinds((prev) => {
                      const next = new Set(prev)
                      if (next.has(f.kind)) next.delete(f.kind)
                      else next.add(f.kind)
                      return next
                    })
                  }
                >
                  <strong>{f.label}</strong>
                  <span className="muted small">{f.description}</span>
                </button>
              ))}
            </div>
            {error && <p className="error">{error}</p>}
            <div className="row">
              <button type="button" onClick={() => void finish()} disabled={busy}>
                {kinds.size === 0 ? 'Just chat' : `Create ${kinds.size} ${kinds.size === 1 ? 'document' : 'documents'}`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export type { SourceKind }
