import { useCallback, useEffect, useState } from 'react'
import { ingest } from '../api/ingest'
import { rag } from '../api/rag'
import type { Citation, Notebook, Output, OutputKind } from '../api/types'
import { OUTPUT_POLL_INTERVAL_MS } from '../config'
import { useAsync } from '../hooks/useAsync'
import { ChatPane } from './ChatPane'
import { NotebookList } from './NotebookList'
import { OutputTiles } from './OutputTiles'
import { OutputViewer } from './OutputViewer'
import { SourcesPane } from './SourcesPane'
import { Wizard } from './Wizard'

const LAST_NOTEBOOK_KEY = 'lasteverlm.notebook'

/** The two-column screen. Left: sources, then the output forms as tiles.
 *  Right: the viewer with one tab per generated document, then the chat. */
export function Workspace() {
  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(LAST_NOTEBOOK_KEY)
    } catch {
      return null
    }
  })
  const [wizardFor, setWizardFor] = useState<string | null>(null)
  const { error, run } = useAsync()

  useEffect(() => {
    void run(async () => {
      const list = await ingest.listNotebooks()
      setNotebooks(list)
      setSelectedId((cur) => (cur && list.some((n) => n.id === cur) ? cur : (list[0]?.id ?? null)))
    })
  }, [run])

  useEffect(() => {
    try {
      if (selectedId) localStorage.setItem(LAST_NOTEBOOK_KEY, selectedId)
    } catch {
      // storage unavailable; the first notebook is selected on the next load
    }
  }, [selectedId])

  /** A new notebook goes straight into the wizard: it is empty otherwise. */
  async function create(title: string) {
    const nb = await run(() => ingest.createNotebook(title))
    if (nb) {
      setNotebooks((prev) => [nb, ...prev])
      setSelectedId(nb.id)
      setWizardFor(nb.id)
    }
  }

  async function remove(id: string) {
    const ok = await run(async () => {
      await ingest.deleteNotebook(id)
      return true
    })
    if (ok) {
      setNotebooks((prev) => {
        const next = prev.filter((n) => n.id !== id)
        setSelectedId((cur) => (cur === id ? (next[0]?.id ?? null) : cur))
        return next
      })
    }
  }

  return (
    <main className="workspace">
      <aside className="sidebar no-print">
        <NotebookList notebooks={notebooks} selectedId={selectedId} onSelect={setSelectedId} onCreate={create} onDelete={remove} />
        {error && <p className="error">{error}</p>}
      </aside>
      {selectedId ? (
        <NotebookView key={selectedId} notebookId={selectedId} wizardOpen={wizardFor === selectedId} onWizard={(open) => setWizardFor(open ? selectedId : null)} />
      ) : (
        <div className="columns empty">
          <p className="muted">Create a notebook to start.</p>
        </div>
      )}
    </main>
  )
}

interface ViewProps {
  notebookId: string
  wizardOpen: boolean
  onWizard: (open: boolean) => void
}

/** Everything that belongs to one notebook; remounted by key on a switch.
 *  Holds the outputs because tiles create them, the viewer shows them and
 *  the chat cites them. */
function NotebookView({ notebookId, wizardOpen, onWizard }: ViewProps) {
  const [outputs, setOutputs] = useState<Output[]>([])
  const [selectedOutput, setSelectedOutput] = useState<string | null>(null)
  const [scope, setScope] = useState<Output | null>(null)
  const [highlight, setHighlight] = useState<string | null>(null)
  const [sourcesVersion, setSourcesVersion] = useState(0)
  const { busy, error, run } = useAsync()

  const reloadOutputs = useCallback(async () => {
    const list = await rag.listOutputs(notebookId)
    setOutputs(list)
    setSelectedOutput((cur) => (cur && list.some((o) => o.id === cur) ? cur : (list[0]?.id ?? null)))
  }, [notebookId])

  useEffect(() => {
    void run(reloadOutputs)
  }, [reloadOutputs, run])

  const pending = outputs.some((o) => o.status === 'processing' || o.status === 'waiting')
  useEffect(() => {
    if (!pending) return
    const t = setInterval(() => {
      rag.listOutputs(notebookId).then(
        (list) => {
          setOutputs(list)
          // a document that just became ready is also a new generated source
          if (list.some((o) => o.status === 'ready') ) setSourcesVersion((v) => v + 1)
        },
        () => {
          // a failed poll is retried on the next tick; user actions surface errors through run()
        },
      )
    }, OUTPUT_POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [pending, notebookId])

  async function createOutput(kind: OutputKind) {
    const created = await run(() => rag.createOutput(notebookId, kind))
    if (created) {
      setOutputs((prev) => [created, ...prev])
      setSelectedOutput(created.id)
    }
  }

  /** A citation into a generated document opens that document's tab (the
   *  output whose generated source it cites); any other citation highlights
   *  the source in the list. */
  const onCitation = useCallback(
    (c: Citation | null) => {
      setHighlight(c?.source_id ?? null)
      if (!c) return
      if (c.source_kind === 'generated') {
        const match = outputs.find((o) => o.source_id === c.source_id)
        if (match) setSelectedOutput(match.id)
      }
      document.getElementById(`source-${c.source_id}`)?.scrollIntoView({ block: 'nearest' })
    },
    [outputs],
  )

  return (
    <div className="columns">
      <div className="column left no-print">
        <SourcesPane notebookId={notebookId} highlightedSourceId={highlight} version={sourcesVersion} onAdd={() => onWizard(true)} />
        <OutputTiles disabled={busy} onCreate={(k) => void createOutput(k)} />
      </div>
      <div className="column right">
        <OutputViewer
          outputs={outputs}
          selectedId={selectedOutput}
          onSelect={setSelectedOutput}
          onChanged={(o) => setOutputs((prev) => prev.map((x) => (x.id === o.id ? o : x)))}
          onDeleted={(id) => {
            setOutputs((prev) => prev.filter((x) => x.id !== id))
            setSourcesVersion((v) => v + 1)
            if (scope?.id === id) setScope(null)
          }}
          onAskAbout={setScope}
          error={error}
        />
        <div className="no-print chat-wrap">
          <ChatPane notebookId={notebookId} scope={scope} onClearScope={() => setScope(null)} onCitationSelected={onCitation} />
        </div>
      </div>
      {wizardOpen && (
        <Wizard
          notebookId={notebookId}
          onClose={() => onWizard(false)}
          onDone={() => {
            onWizard(false)
            setSourcesVersion((v) => v + 1)
            void run(reloadOutputs)
          }}
        />
      )}
    </div>
  )
}
