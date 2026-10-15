import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { admin } from '../api/admin'
import { ingest } from '../api/ingest'
import { rag } from '../api/rag'
import type { Notebook } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useMe } from '../hooks/useMe'
import { canSeeAdmin, canWriteAdmin } from '../lib/roles'
import { browserStorage, readWidth, SIDEBAR_WIDTH, writeWidth } from '../lib/layout'
import { readLastNotebook, writeLastNotebook } from '../lib/lastNotebook'
import { firstSelection } from '../lib/firstRun'
import { tourDone } from '../lib/tour'
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
  // the notebook the add-sources dialog is open for
  const [wizardFor, setWizardFor] = useState<string | null>(null)
  // the notebook list's width, remembered per browser; null is the stylesheet's
  const [sidebarWidth, setSidebarWidth] = useState(() => readWidth(browserStorage(), SIDEBAR_WIDTH.key, SIDEBAR_WIDTH.min, SIDEBAR_WIDTH.max))
  const workspaceRef = useRef<HTMLElement>(null)
  const { error, run } = useAsync()
  // a notebook with generated documents asks what becomes of them
  const [deleting, setDeleting] = useState<{ notebook: Notebook; outputs: number } | null>(null)

  // the introduction still to show: without a notebook the workspace makes one, so the tour runs
  const { me } = useMe()
  const tourPending = !tourDone(me, browserStorage())
  const madeFirst = useRef(false)

  useEffect(() => {
    void run(async () => {
      const list = await ingest.listNotebooks()
      setNotebooks(list)
      const pick = firstSelection(
        list.map((n) => n.id),
        readLastNotebook(),
        tourPending,
      )
      setSelectedId(pick.select)
      if (pick.createFirst && !madeFirst.current) {
        madeFirst.current = true
        // no add-sources dialog over it: the tour's first step points at "+ add"
        const nb = await ingest.createNotebook(t('nb.firstTitle'))
        setNotebooks([nb])
        setSelectedId(nb.id)
      }
    })
    // the account is known before the workspace mounts; the list loads once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run])

  useEffect(() => {
    if (selectedId) writeLastNotebook(selectedId)
  }, [selectedId])

  // the starter notebook, marked in the list for admins and viewers; only an admin sets it
  const seesStarter = canSeeAdmin(me)
  const [starterId, setStarterId] = useState<string | null>(null)
  useEffect(() => {
    if (!seesStarter) return
    admin.getStarter().then(
      (s) => setStarterId(s.notebook_id),
      () => {
        // no mark without the setting; the admin pages show the error
      },
    )
  }, [seesStarter])

  /** The account service refuses a notebook whose sources are not all
   *  ready, or one an admin does not own; its sentence is shown. */
  async function makeStarter(id: string) {
    const notebook = notebooks.find((n) => n.id === id)
    if (!notebook || !confirm(t('starter.confirm', { title: notebook.title }))) return
    const s = await run(() => admin.setStarter(id))
    if (s) setStarterId(s.notebook_id)
  }

  /** A new notebook goes straight into adding sources: it is empty otherwise. */
  async function create(title: string) {
    const nb = await run(() => ingest.createNotebook(title))
    if (nb) {
      setNotebooks((prev) => [nb, ...prev])
      setSelectedId(nb.id)
      setWizardFor(nb.id)
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
        <NotebookList
          notebooks={notebooks}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onCreate={create}
          onDelete={remove}
          onRename={(id, title) => void rename(id, title)}
          onShared={(id, token) => setNotebooks((prev) => prev.map((n) => (n.id === id ? { ...n, share_token: token } : n)))}
          starterId={seesStarter ? starterId : null}
          onMakeStarter={canWriteAdmin(me) ? (id) => void makeStarter(id) : undefined}
        />
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
        <NotebookView key={selectedId} notebookId={selectedId} wizard={wizardFor === selectedId}
          onWizard={(open) => setWizardFor(open ? selectedId : null)}
        />
      ) : (
        <div className="columns empty">
          <p className="muted">{t('nb.createFirst')}</p>
        </div>
      )}
    </main>
  )
}
