import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { ingest } from '../api/ingest'
import { rag } from '../api/rag'
import type { Notebook } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { browserStorage, readWidth, SIDEBAR_WIDTH, writeWidth } from '../lib/layout'
import { readLastNotebook, writeLastNotebook } from '../lib/lastNotebook'
import { ColumnDivider } from './ColumnDivider'
import { NotebookDeleteDialog } from './NotebookDeleteDialog'
import { NotebookList } from './NotebookList'
import { t } from '../i18n'
import { NotebookView } from './NotebookView'

/** The two-column screen. Left: sources, then the output forms as tiles.
 *  Right: the viewer with one tab per generated document, then the chat. */
export function Workspace() {
  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(readLastNotebook)
  // the notebook the wizard is open for; fresh = just created, so it asks for outputs too
  const [wizardFor, setWizardFor] = useState<{ id: string; fresh: boolean } | null>(null)
  // the notebook list's width, remembered per browser; null is the stylesheet's
  const [sidebarWidth, setSidebarWidth] = useState(() => readWidth(browserStorage(), SIDEBAR_WIDTH.key, SIDEBAR_WIDTH.min, SIDEBAR_WIDTH.max))
  const workspaceRef = useRef<HTMLElement>(null)
  const { error, run } = useAsync()
  // a notebook with generated documents asks what becomes of them
  const [deleting, setDeleting] = useState<{ notebook: Notebook; outputs: number } | null>(null)

  useEffect(() => {
    void run(async () => {
      const list = await ingest.listNotebooks()
      setNotebooks(list)
      setSelectedId((cur) => (cur && list.some((n) => n.id === cur) ? cur : (list[0]?.id ?? null)))
    })
  }, [run])

  useEffect(() => {
    if (selectedId) writeLastNotebook(selectedId)
  }, [selectedId])

  /** A new notebook goes straight into the wizard: it is empty otherwise. */
  async function create(title: string) {
    const nb = await run(() => ingest.createNotebook(title))
    if (nb) {
      setNotebooks((prev) => [nb, ...prev])
      setSelectedId(nb.id)
      setWizardFor({ id: nb.id, fresh: true })
    }
  }

  /** Without generated documents a plain confirmation; with some, a dialog
   *  asks whether they go too or stay in the library. Their number comes
   *  from rag; when it cannot be read nothing is deleted. */
  async function remove(id: string) {
    const notebook = notebooks.find((n) => n.id === id)
    if (!notebook) return
    const outputs = await run(() => rag.listOutputs(id))
    if (!outputs) return
    if (outputs.length > 0) {
      setDeleting({ notebook, outputs: outputs.length })
      return
    }
    if (!confirm(t('nb.deleteConfirm', { title: notebook.title }))) return
    if (await run(() => ingest.deleteNotebook(id).then(() => true))) dropNotebook(id)
  }

  /** Shown at once; the stored title replaces it, the old one returns on error. */
  async function rename(id: string, title: string) {
    const old = notebooks.find((n) => n.id === id)
    if (!old) return
    setNotebooks((prev) => prev.map((n) => (n.id === id ? { ...n, title } : n)))
    const saved = await run(() => ingest.renameNotebook(id, title))
    setNotebooks((prev) => prev.map((n) => (n.id === id ? (saved ?? old) : n)))
  }

  function dropNotebook(id: string) {
    setNotebooks((prev) => {
      const next = prev.filter((n) => n.id !== id)
      setSelectedId((cur) => (cur === id ? (next[0]?.id ?? null) : cur))
      return next
    })
  }

  return (
    <main className="workspace" ref={workspaceRef} style={sidebarWidth === null ? undefined : ({ '--sidebar-w': `${sidebarWidth}px` } as CSSProperties)}>
      <aside className="sidebar no-print">
        <NotebookList notebooks={notebooks} selectedId={selectedId} onSelect={setSelectedId} onCreate={create} onDelete={remove} onRename={(id, title) => void rename(id, title)} />
        {error && <p className="error">{error}</p>}
      </aside>
      {deleting && (
        <NotebookDeleteDialog
          notebook={deleting.notebook}
          outputs={deleting.outputs}
          onCancel={() => setDeleting(null)}
          onDeleted={(id) => {
            setDeleting(null)
            dropNotebook(id)
          }}
        />
      )}
      <ColumnDivider
        label={t('ws.resizeList')}
        width={sidebarWidth}
        min={SIDEBAR_WIDTH.min}
        max={() => SIDEBAR_WIDTH.max}
        origin={() => workspaceRef.current?.getBoundingClientRect().left ?? 0}
        onChange={setSidebarWidth}
        onCommit={(px) => writeWidth(browserStorage(), SIDEBAR_WIDTH.key, px)}
        onReset={() => {
          setSidebarWidth(null)
          writeWidth(browserStorage(), SIDEBAR_WIDTH.key, null)
        }}
      />
      {selectedId ? (
        <NotebookView key={selectedId} notebookId={selectedId} wizard={wizardFor?.id === selectedId ? wizardFor : null}
          onWizard={(open) => setWizardFor(open ? { id: selectedId, fresh: false } : null)}
        />
      ) : (
        <div className="columns empty">
          <p className="muted">{t('nb.createFirst')}</p>
        </div>
      )}
    </main>
  )
}
