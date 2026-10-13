import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { ingest } from '../api/ingest'
import { rag } from '../api/rag'
import type { Citation, Notebook, Output, OutputKind, OutputOptions, Source } from '../api/types'
import { OUTPUT_POLL_INTERVAL_MS } from '../config'
import { useAsync } from '../hooks/useAsync'
import {
  CHAT_PRESETS,
  activePreset,
  browserStorage,
  DEFAULT_VIEWER_RATIO,
  LEFT_WIDTH,
  MIN_RIGHT_WIDTH,
  presetRatio,
  readRatio,
  readWidth,
  SIDEBAR_WIDTH,
  writeRatio,
  writeWidth,
} from '../lib/layout'
import { DEMO_QUESTION } from '../lib/demo'
import { readLastNotebook, writeLastNotebook } from '../lib/lastNotebook'
import { formFor } from '../lib/outputs'
import { ChatPane } from './ChatPane'
import { ColumnDivider } from './ColumnDivider'
import { Divider } from './Divider'
import { NotebookList } from './NotebookList'
import { OutputsPane } from './OutputsPane'
import { OutputTiles } from './OutputTiles'
import { OutputViewer } from './OutputViewer'
import { SourcesPane } from './SourcesPane'
import { Wizard } from './Wizard'
import { t } from '../i18n'

/** The two-column screen. Left: sources, then the output forms as tiles.
 *  Right: the viewer with one tab per generated document, then the chat. */
export function Workspace() {
  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(readLastNotebook)
  const [wizardFor, setWizardFor] = useState<string | null>(null)
  // the notebook list's width, remembered per browser; null is the stylesheet's
  const [sidebarWidth, setSidebarWidth] = useState(() => readWidth(browserStorage(), SIDEBAR_WIDTH.key, SIDEBAR_WIDTH.min, SIDEBAR_WIDTH.max))
  const workspaceRef = useRef<HTMLElement>(null)
  const { error, run } = useAsync()

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
    <main className="workspace" ref={workspaceRef} style={sidebarWidth === null ? undefined : ({ '--sidebar-w': `${sidebarWidth}px` } as CSSProperties)}>
      <aside className="sidebar no-print">
        <NotebookList notebooks={notebooks} selectedId={selectedId} onSelect={setSelectedId} onCreate={create} onDelete={remove} />
        {error && <p className="error">{error}</p>}
      </aside>
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
        <NotebookView key={selectedId} notebookId={selectedId} wizardOpen={wizardFor === selectedId} onWizard={(open) => setWizardFor(open ? selectedId : null)} />
      ) : (
        <div className="columns empty">
          <p className="muted">{t('nb.createFirst')}</p>
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
  // the picked output format, kept while this notebook is open
  const [format, setFormat] = useState<OutputKind | null>(null)
  // the uploads as last listed, null until the first list arrived
  const [uploads, setUploads] = useState<Source[] | null>(null)
  const [outputsLoaded, setOutputsLoaded] = useState(false)
  const hasReadySource = uploads?.some((s) => s.status === 'ready') ?? false
  // viewer/chat split, remembered per browser; full view hides the chat behind a toggle
  const [ratio, setRatio] = useState(() => readRatio(browserStorage()))
  const [fullView, setFullView] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const rightColumn = useRef<HTMLDivElement>(null)
  // the left column's width (sources, formats, outputs), remembered per browser
  const [leftWidth, setLeftWidth] = useState(() => readWidth(browserStorage(), LEFT_WIDTH.key, LEFT_WIDTH.min, LEFT_WIDTH.max))
  const columnsRef = useRef<HTMLDivElement>(null)

  const leaveFullView = useCallback(() => {
    setFullView(false)
    setChatOpen(false)
  }, [])

  // Esc closes the chat of the full view first, then the full view itself
  useEffect(() => {
    if (!fullView) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (chatOpen) setChatOpen(false)
      else leaveFullView()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [fullView, chatOpen, leaveFullView])
  const { busy, error, run } = useAsync()

  const reloadOutputs = useCallback(async () => {
    const list = await rag.listOutputs(notebookId)
    setOutputs(list)
    setOutputsLoaded(true)
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
        (list) => setOutputs(list),
        () => {
          // a failed poll is retried on the next tick; user actions surface errors through run()
        },
      )
    }, OUTPUT_POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [pending, notebookId])

  function removeOutput(id: string) {
    setOutputs((prev) => prev.filter((x) => x.id !== id))
    if (scope?.id === id) setScope(null)
  }

  async function deleteOutput(o: Output) {
    if (!confirm(t('ws.deleteDoc', { title: o.title || formFor(o.kind).label }))) return
    const ok = await run(async () => {
      await rag.deleteOutput(o.id)
      return true
    })
    if (ok) removeOutput(o.id)
  }

  async function createOutput(kind: OutputKind, options: OutputOptions) {
    const created = await run(() => rag.createOutput(notebookId, kind, options))
    if (created) {
      setOutputs((prev) => [created, ...prev])
      setSelectedOutput(created.id)
    }
  }

  /** Every source a citation can still point to: the uploads and the
   *  generated documents of this notebook; null while either is loading. */
  const presentSources =
    uploads && outputsLoaded
      ? new Set([
          // citations carry the notebook's link id (Source.id), never the library id
          ...uploads.map((s) => s.id),
          ...outputs.flatMap((o) => (o.source_id ? [o.source_id] : [])),
        ])
      : null

  /** A citation into a generated document opens that document's tab (the
   *  output whose generated source it cites) and shows it in the Outputs
   *  list; any other citation highlights the source in the Sources list. */
  const onCitation = useCallback(
    (c: Citation | null) => {
      setHighlight(c?.source_id ?? null)
      if (!c) return
      if (c.source_kind === 'generated') {
        const match = outputs.find((o) => o.source_id === c.source_id)
        if (match) {
          setSelectedOutput(match.id)
          document.getElementById(`output-${match.id}`)?.scrollIntoView({ block: 'nearest' })
        }
        return
      }
      document.getElementById(`source-${c.source_id}`)?.scrollIntoView({ block: 'nearest' })
    },
    [outputs],
  )

  return (
    <div
      ref={columnsRef}
      className={['columns', fullView ? 'full' : '', fullView && chatOpen ? 'chat-open' : ''].join(' ').trim()}
      style={leftWidth === null ? undefined : ({ '--left-w': `${leftWidth}px` } as CSSProperties)}
    >
      <div className="column left no-print">
        <SourcesPane
          notebookId={notebookId}
          highlightedSourceId={highlight}
          version={sourcesVersion}
          onAdd={() => onWizard(true)}
          onSourcesChange={setUploads}
        />
        <OutputTiles
          selected={format}
          hasReadySource={hasReadySource}
          busy={busy}
          onSelect={setFormat}
          onCreate={(k, o) => void createOutput(k, o)}
        />
        <OutputsPane outputs={outputs} selectedId={selectedOutput} onOpen={setSelectedOutput} onDelete={(o) => void deleteOutput(o)} />
      </div>
      <ColumnDivider
        label={t('ws.resizeLeft')}
        width={leftWidth}
        min={LEFT_WIDTH.min}
        max={() => {
          const total = columnsRef.current?.getBoundingClientRect().width ?? 0
          return Math.max(LEFT_WIDTH.min, Math.min(LEFT_WIDTH.max, total - MIN_RIGHT_WIDTH))
        }}
        origin={() => columnsRef.current?.getBoundingClientRect().left ?? 0}
        onChange={setLeftWidth}
        onCommit={(px) => writeWidth(browserStorage(), LEFT_WIDTH.key, px)}
        onReset={() => {
          setLeftWidth(null)
          writeWidth(browserStorage(), LEFT_WIDTH.key, null)
        }}
      />
      <div className="column right" ref={rightColumn}>
        <OutputViewer
          outputs={outputs}
          selectedId={selectedOutput}
          onSelect={setSelectedOutput}
          onChanged={(o) => setOutputs((prev) => prev.map((x) => (x.id === o.id ? o : x)))}
          onDeleted={removeOutput}
          onAskAbout={(o) => {
            setScope(o)
            if (fullView) setChatOpen(true)
          }}
          error={error}
          fullView={fullView}
          onFullView={(on) => (on ? setFullView(true) : leaveFullView())}
          chatOpen={chatOpen}
          onToggleChat={() => setChatOpen((v) => !v)}
          style={fullView ? undefined : { flexBasis: `${ratio * 100}%` }}
        />
        {!fullView && (
          <Divider
            ratio={ratio}
            container={() => rightColumn.current}
            onChange={setRatio}
            onCommit={(r) => writeRatio(browserStorage(), r)}
            onReset={() => {
              setRatio(DEFAULT_VIEWER_RATIO)
              writeRatio(browserStorage(), null)
            }}
          />
        )}
        <div className="no-print chat-wrap">
          <ChatPane
            notebookId={notebookId}
            scope={scope}
            presentSources={presentSources}
            suggestion={uploads?.some((s) => s.demo) ? DEMO_QUESTION : undefined}
            onClearScope={() => setScope(null)}
            onCitationSelected={onCitation}
            tools={
              fullView ? undefined : (
                <span className="presets" role="group" aria-label={t('ws.chatHeight')}>
                  {CHAT_PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      className={activePreset(ratio) === p.label ? 'preset active' : 'preset'}
                      aria-pressed={activePreset(ratio) === p.label}
                      title={t('ws.chatAt', { pct: Math.round(p.chat * 100) })}
                      onClick={() => {
                        const r = presetRatio(p.chat)
                        setRatio(r)
                        writeRatio(browserStorage(), r)
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </span>
              )
            }
          />
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
