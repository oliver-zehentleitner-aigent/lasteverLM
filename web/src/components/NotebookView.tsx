import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { rag } from '../api/rag'
import type { Citation, Output, OutputKind, OutputOptions, Source } from '../api/types'
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
  writeRatio,
  writeWidth,
} from '../lib/layout'
import { DEMO_QUESTION } from '../lib/demo'
import { formFor } from '../lib/outputs'
import type { LocateRequest } from '../lib/locate'
import { readExcluded, selection, toggled, writeExcluded } from '../lib/sourceSelection'
import { takeOpenOutput } from '../lib/lastNotebook'
import { citationTarget } from '../lib/openEntry'
import { ChatPane } from './ChatPane'
import { ColumnDivider } from './ColumnDivider'
import { Divider } from './Divider'
import { OutputsPane } from './OutputsPane'
import { OutputTiles } from './OutputTiles'
import { OutputViewer } from './OutputViewer'
import { SourcesPane } from './SourcesPane'
import { Wizard } from './Wizard'
import { t } from '../i18n'

interface ViewProps {
  notebookId: string
  /** open with the output step (fresh) or without it; null when closed */
  wizard: { fresh: boolean } | null
  onWizard: (open: boolean) => void
}

/** Everything that belongs to one notebook; remounted by key on a switch.
 *  Holds the outputs because tiles create them, the viewer shows them and
 *  the chat cites them. */
export function NotebookView({ notebookId, wizard, onWizard }: ViewProps) {
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
  // the sources turned off for the chat and new documents, remembered per notebook
  const [excluded, setExcluded] = useState(() => readExcluded(browserStorage(), notebookId))
  const changeExcluded = (next: Set<string>) => {
    setExcluded(next)
    writeExcluded(browserStorage(), notebookId, next)
  }
  const picked = selection(uploads?.map((s) => s.id) ?? [], excluded)
  const hasReadySource = uploads?.some((s) => s.status === 'ready' && !excluded.has(s.id)) ?? false
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

  // the document the library asked to open, selected once the list is in
  const requested = useRef<string | null>(takeOpenOutput())
  const reloadOutputs = useCallback(async () => {
    const list = await rag.listOutputs(notebookId)
    setOutputs(list)
    setOutputsLoaded(true)
    const wanted = requested.current
    requested.current = null
    setSelectedOutput((cur) => (cur && list.some((o) => o.id === cur) ? cur : wanted && list.some((o) => o.id === wanted) ? wanted : (list[0]?.id ?? null)))
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
    const created = await run(() => rag.createOutput(notebookId, kind, options, picked.sourceIds))
    if (created) {
      setOutputs((prev) => [created, ...prev])
      setSelectedOutput(created.id)
    }
  }

  const ownGenerated = useMemo(
    () => (outputsLoaded ? new Set(outputs.flatMap((o) => (o.source_id ? [o.source_id] : []))) : null),
    [outputs, outputsLoaded],
  )

  /** A new title, shown at once; the stored output replaces it, the old
   *  one returns on error. From the outputs list and the tabs alike. */
  async function renameOutput(o: Output, title: string) {
    setOutputs((prev) => prev.map((x) => (x.id === o.id ? { ...x, title } : x)))
    const saved = await run(() => rag.renameOutput(o.id, title))
    setOutputs((prev) => prev.map((x) => (x.id === o.id ? (saved ?? o) : x)))
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
          return
        }
        // a document added from the library is listed among the sources
      }
      document.getElementById(`source-${c.source_id}`)?.scrollIntoView({ block: 'nearest' })
    },
    [outputs],
  )

  /** "Open document" on a citation into a generated document: that
   *  document's tab, and a request for the viewer to show the passage. An
   *  upload's "open in source" opens it in a new tab (a PDF on the cited
   *  page) when it has a preview, and highlights it in the list either way. */
  const [locate, setLocate] = useState<LocateRequest | null>(null)
  function openSource(c: Citation) {
    if (c.source_kind !== 'generated') {
      const href = citationTarget(uploads?.find((s) => s.id === c.source_id), c.page)
      if (href) window.open(href, '_blank', 'noopener,noreferrer')
      onCitation(c)
      return
    }
    const match = outputs.find((o) => o.source_id === c.source_id)
    if (!match) {
      // made in another notebook and added from the library: shown in the sources list
      onCitation(c)
      return
    }
    setSelectedOutput(match.id)
    setLocate((prev) => ({ outputId: match.id, text: c.quote, nonce: (prev?.nonce ?? 0) + 1 }))
  }

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
          excluded={excluded}
          onToggle={(id) => changeExcluded(toggled(excluded, id))}
          onAll={(on) => changeExcluded(on ? new Set() : new Set(uploads?.map((s) => s.id) ?? []))}
          ownGenerated={ownGenerated}
          onSourcesChange={setUploads}
        />
        <OutputTiles
          notebookId={notebookId}
          selected={format}
          hasReadySource={hasReadySource}
          noneSelected={picked.total > 0 && picked.selected === 0}
          busy={busy}
          onSelect={setFormat}
          onCreate={(k, o) => void createOutput(k, o)}
        />
        <OutputsPane outputs={outputs} sources={uploads} selectedId={selectedOutput} onOpen={setSelectedOutput} onDelete={(o) => void deleteOutput(o)} onRename={(o, title) => void renameOutput(o, title)} />
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
          sources={uploads}
          outputs={outputs}
          selectedId={selectedOutput}
          onSelect={setSelectedOutput}
          onChanged={(o) => setOutputs((prev) => prev.map((x) => (x.id === o.id ? o : x)))}
          onRename={(o, title) => void renameOutput(o, title)}
          onDeleted={removeOutput}
          locate={locate && locate.outputId === selectedOutput ? locate : null}
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
          onOpenSource={openSource}
          presentSources={presentSources}
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
            sources={picked}
            suggestion={uploads?.some((s) => s.demo) ? DEMO_QUESTION : undefined}
            onClearScope={() => setScope(null)}
            onCitationSelected={onCitation}
            onOpenSource={openSource}
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
      {wizard && (
        <Wizard
          notebookId={notebookId}
          withOutputs={wizard.fresh}
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
