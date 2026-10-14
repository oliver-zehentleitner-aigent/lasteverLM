import { useState, type DragEvent } from 'react'
import { ingest } from '../api/ingest'
import type { LibraryEntry, SourceKind } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useMe } from '../hooks/useMe'
import { CAPTURE_MODES, preferredCapture, type CaptureMode } from '../lib/capture'
import { filterLibrary, notInNotebook, shortUrl } from '../lib/library'
import { SOURCE_FORMS, sourceKindLabel, tileNote, type SourceForm } from '../lib/outputs'
import { StarterBadge } from './StarterBadge'
import { ImageName } from './ImageName'
import { t, tn } from '../i18n'

interface Props {
  notebookId: string
  /** sources went in: the list reloads while the dialog stays open */
  onAdded: () => void
  onClose: () => void
}

type Step = 1 | 2

/** Adding sources: what goes in (the kind tiles, or from the library),
 *  then how (files, pasted text, an address, or the library's entries),
 *  uploaded per file as soon as the user confirms. It then returns to the
 *  tiles with a note on what went in, to add more, until the user closes
 *  it. Outputs are made in the Output format area, never here. */
export function Wizard({ notebookId, onAdded, onClose }: Props) {
  const [step, setStep] = useState<Step>(1)
  // what this dialog added so far, and how many of the last batch were there already
  const [addedTotal, setAddedTotal] = useState(0)
  const [form, setForm] = useState<SourceForm | null>(null)
  // "from library": entries of the user's library not yet in this notebook
  const [fromLibrary, setFromLibrary] = useState(false)
  const [library, setLibrary] = useState<LibraryEntry[] | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [libraryQuery, setLibraryQuery] = useState('')
  const [existing, setExisting] = useState(0)
  const [files, setFiles] = useState<File[]>([])
  const [pasted, setPasted] = useState('')
  const [url, setUrl] = useState('')
  const [uploaded, setUploaded] = useState(0)
  const { busy, error, run } = useAsync()
  const { me } = useMe()
  // how PDFs are read, preset from the preference
  const [capture, setCapture] = useState<CaptureMode>(() => preferredCapture(me?.preferences))

  const canUpload = fromLibrary
    ? picked.size > 0
    : form?.input === 'url'
      ? url.trim() !== ''
      : files.length > 0 || pasted.trim() !== ''

  async function openLibrary() {
    setFromLibrary(true)
    setForm(null)
    setStep(2)
    const list = await run(() => ingest.listLibrary())
    if (list) setLibrary(notInNotebook(list, notebookId))
  }

  async function upload() {
    if (!form && !fromLibrary) return
    const ok = await run(async () => {
      let n = 0
      let already = 0
      const count = (r: { existing: boolean }) => {
        n += 1
        if (r.existing) already += 1
        setUploaded(n)
        setExisting(already)
      }
      if (fromLibrary) {
        for (const id of picked) count(await ingest.addFromLibrary(notebookId, id))
        return { n, already }
      }
      if (form?.input === 'url') {
        count(await ingest.addUrl(notebookId, url.trim()))
        return { n, already }
      }
      // a file that went in leaves the list, so after a failure (a storage
      // outage answers 503) only the rest is retried and stays selected
      for (const f of files) {
        count(await ingest.uploadFile(notebookId, f, capture))
        setFiles((prev) => prev.filter((x) => x !== f))
      }
      if (pasted.trim()) {
        const name = `${pasted.trim().split('\n')[0].slice(0, 40) || t('wiz.pastedName')}.txt`
        count(await ingest.uploadFile(notebookId, new File([pasted], name, { type: 'text/plain' })))
        setPasted('')
      }
      return { n, already }
    })
    if (ok === undefined) return
    // back to the tiles for more; the list behind shows the new ones
    setAddedTotal((total) => total + ok.n - ok.already)
    setExisting(ok.already)
    setForm(null)
    setFromLibrary(false)
    setPicked(new Set())
    setUrl('')
    setStep(1)
    onAdded()
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
          <strong>{t('wiz.title')}</strong>
          <button type="button" className="icon" onClick={onClose} title={t('common.close')}>
            ×
          </button>
        </header>

        {step === 1 && (
          <>
            <h2>{t('wiz.whatIn')}</h2>
            <div className="tile-grid">
              <button type="button" className="tile" onClick={() => void openLibrary()}>
                <strong>{t('wiz.fromLibrary')}</strong>
                <span className="muted small">{t('wiz.fromLibrary.note')}</span>
              </button>
              {SOURCE_FORMS.map((f) => (
                <button
                  key={f.kind}
                  type="button"
                  className="tile"
                  disabled={!f.available}
                  onClick={() => {
                    setFromLibrary(false)
                    setForm(f)
                    setStep(2)
                  }}
                >
                  <strong>{f.label}</strong>
                  <span className="muted small">{tileNote(f)}</span>
                </button>
              ))}
            </div>
            {addedTotal > 0 && <p className="muted small">{tn('wiz.addedSoFar', addedTotal)}</p>}
            {existing > 0 && <p className="muted small">{tn('wiz.existing', existing)}</p>}
            <div className="row wizard-done">
              <button type="button" className={addedTotal > 0 ? undefined : 'secondary'} onClick={onClose}>
                {addedTotal > 0 ? t('common.done') : t('common.close')}
              </button>
            </div>
          </>
        )}

        {step === 2 && fromLibrary && (
          <>
            <h2>{t('wiz.whichFromLibrary')}</h2>
            <input
              type="search"
              placeholder={t('wiz.filterLibrary')}
              value={libraryQuery}
              onChange={(e) => setLibraryQuery(e.target.value)}
              aria-label={t('wiz.filterLibraryLabel')}
            />
            {library === null && !error && <p className="muted">{t('common.loading')}</p>}
            {library && library.length === 0 && <p className="muted">{t('wiz.allInNotebook')}</p>}
            {library && library.length > 0 && (
              <ul className="list library-pick">
                {filterLibrary(library, { kind: 'all', query: libraryQuery }).map((e) => (
                  <li key={e.id}>
                    <label className={picked.has(e.id) ? 'pick picked' : 'pick'}>
                      <input
                        type="checkbox"
                        checked={picked.has(e.id)}
                        onChange={() =>
                          setPicked((prev) => {
                            const next = new Set(prev)
                            if (next.has(e.id)) next.delete(e.id)
                            else next.add(e.id)
                            return next
                          })
                        }
                      />
                      <span className="pick-name">
                        <ImageName kind={e.kind} previewUrl={e.preview_url} label={e.url ? shortUrl(e.url) : e.name} title={e.url ?? e.name} />
                      </span>
                      <span className="pick-badges">
                        <StarterBadge item={e} />
                        <span className="badge">{sourceKindLabel(e.kind)}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            {busy && uploaded > 0 && <p className="muted">{t('wiz.adding', { n: uploaded })}</p>}
            {error && <p className="error">{error}</p>}
            <div className="row">
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setFromLibrary(false)
                  setStep(1)
                }}
                disabled={busy}
              >
                {t('common.back')}
              </button>
              {picked.size > 0 && <span className="muted small">{t('wiz.selected', { n: picked.size })}</span>}
              <button type="button" onClick={() => void upload()} disabled={busy || !canUpload}>
                {t('common.add')}
              </button>
            </div>
          </>
        )}

        {step === 2 && form && !fromLibrary && (
          <>
            <h2>{t('wiz.howIn')}</h2>
            {form.input === 'files' && (
              <div
                className="drop"
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDrop}
              >
                <p>{t('wiz.dropFiles', { kind: form.label })}</p>
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
                {form.kind === 'pdf' && (
                  <fieldset className="capture">
                    <legend>{t('wiz.capture')}</legend>
                    {CAPTURE_MODES.map((m) => (
                      <label key={m.mode} className="check">
                        <input type="radio" name="capture" value={m.mode} checked={capture === m.mode} onChange={() => setCapture(m.mode)} />
                        <span>
                          <strong>{m.label}</strong> <span className="muted small">{m.explain}</span>
                        </span>
                      </label>
                    ))}
                  </fieldset>
                )}
                {form.kind === 'text' && (
                  <label>
                    {t('wiz.orPaste')}
                    <textarea rows={5} value={pasted} onChange={(e) => setPasted(e.target.value)} />
                  </label>
                )}
              </div>
            )}
            {form.input === 'url' && (
              <label>
                {t('wiz.address')}
                <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" autoFocus />
              </label>
            )}
            {busy && <p className="muted">{t('wiz.uploading', { n: uploaded })}</p>}
            {error && !busy && files.length > 0 && <p className="muted small">{tn('wiz.retryLeft', files.length)}</p>}
            {error && <p className="error">{error}</p>}
            <div className="row">
              <button type="button" className="secondary" onClick={() => setStep(1)} disabled={busy}>
                {t('common.back')}
              </button>
              <button type="button" onClick={() => void upload()} disabled={busy || !canUpload}>
                {t('common.add')}
              </button>
            </div>
          </>
        )}

      </div>
    </div>
  )
}

export type { SourceKind }
