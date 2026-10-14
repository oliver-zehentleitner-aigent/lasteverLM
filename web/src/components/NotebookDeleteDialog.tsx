import { ingest } from '../api/ingest'
import { rag } from '../api/rag'
import type { Notebook } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { t, tn } from '../i18n'

interface Props {
  notebook: Notebook
  /** how many generated documents the notebook has, more than none */
  outputs: number
  onCancel: () => void
  onDeleted: (id: string) => void
}

/** Deleting a notebook that has generated documents: they go with it, or
 *  they stay in the library (documents belong to the user, not to the
 *  notebook). "Delete them too" removes them in rag first, so a failure
 *  there leaves the notebook untouched; the error stays in the dialog. */
export function NotebookDeleteDialog({ notebook, outputs, onCancel, onDeleted }: Props) {
  const { busy, error, run } = useAsync()

  async function remove(withOutputs: boolean) {
    const ok = await run(async () => {
      if (withOutputs) await rag.deleteNotebookOutputs(notebook.id)
      await ingest.deleteNotebook(notebook.id)
      return true
    })
    if (ok) onDeleted(notebook.id)
  }

  return (
    <div className="backdrop" onClick={busy ? undefined : onCancel}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="delete-notebook-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="delete-notebook-title">{t('nbDel.title', { title: notebook.title })}</h2>
        <p>{tn('nbDel.question', outputs)}</p>
        <p className="muted small">{t('nbDel.rest')}</p>
        {error && <p className="error">{error}</p>}
        <div className="row wrap">
          <button type="button" className="secondary" disabled={busy} onClick={onCancel}>
            {t('common.cancel')}
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={() => void remove(false)}>
            {t('nbDel.keep')}
          </button>
          <button type="button" className="danger" disabled={busy} onClick={() => void remove(true)}>
            {tn('nbDel.all', outputs)}
          </button>
        </div>
      </div>
    </div>
  )
}
