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
import { formFor } from '../lib/outputs'
import type { LocateRequest } from '../lib/locate'
import { readExcluded, selection, toggled, writeExcluded } from '../lib/sourceSelection'
import { takeOpenOutput } from '../lib/lastNotebook'
import { awaitsStarterOutputs, pollStarterOutputs } from '../lib/starterOutputs'
import { afterClose, dropMissing, heldUrl, openTab, tabUrl, readTabs, sessionStore, tabKey, writeTabs, type ViewerTab, tabsToClose } from '../lib/viewerTabs'
import { ChatPane } from './ChatPane'
import { SourceInfo, SourceLinks } from './SourceLinks'
import { citationTarget } from '../lib/openEntry'
import { ColumnDivider } from './ColumnDivider'
import { RowDivider } from './RowDivider'
import { useMe } from '../hooks/useMe'
import { clampHeight, maxHeight, readLeftSizes, writeLeftSizes } from '../lib/leftSizes'
import { Divider } from './Divider'
import { OutputsPane } from './OutputsPane'
import { OutputTiles } from './OutputTiles'
import { OutputViewer } from './OutputViewer'
import { SourcesPane } from './SourcesPane'
import { Wizard } from './Wizard'
import { Tour } from './Tour'
import { t } from '../i18n'
import { docTitle, useDocumentTitle } from '../lib/docTitle'
import { outputsFinished, requestBalanceRefresh, useBalanceActivity } from '../lib/balance'

interface ViewProps {
  notebookId: string
  /** for the browser tab's title */
  notebookTitle: string
  /** the add-sources dialog is open */
  wizard: boolean
  onWizard: (open: boolean) => void
}

/** Everything that belongs to one notebook; remounted by key on a switch.
 *  Holds the outputs because tiles create them, the viewer shows them and
 *  the chat cites them. */
export function NotebookView({ notebookId, notebookTitle, wizard, onWizard }: ViewProps) {
  const [outputs, setOutputs] = useState<Output[]>([])
  // the viewer's tabs: what was opened, in that order, kept for the browser session
  const [tabs, setTabs] = useState<ViewerTab[]>(() => readTabs(sessionStore(), notebookId).tabs)
  const [activeKey, setActiveKey] = useState<string | null>(() => readTabs(sessionStore(), notebookId).active)
  useEffect(() => writeTabs(sessionStore(), notebookId, { tabs, active: activeKey }), [notebookId, tabs, activeKey])
  const open = useCallback((tab: ViewerTab) => {
    setTabs((prev) => openTab(prev, tab))
    setActiveKey(tabKey(tab))
  }, [])
  function closeTab(key: string) {
    setActiveKey((cur) => (cur === key ? afterClose(tabs.map(tabKey), key) : cur))
    setTabs((prev) => prev.filter((x) => tabKey(x) !== key))
  }
  /** close all, the others or those to the right; no confirmation, every tab can be opened again */
  function closeTabs(which: 'all' | 'others' | 'right', key: string | null) {
    const keys = tabs.map(tabKey)
    const closing = tabsToClose(keys, key, which)
    if (closing.length === 0) return
    // the tab the command was given on stays and comes to the front if the active one went
    setActiveKey((cur) => (which === 'all' ? null : cur !== null && closing.includes(cur) ? key : cur))
    setTabs((prev) => prev.filter((x) => !closing.includes(tabKey(x))))
  }
  const openOutput = useCallback((id: string) => open({ type: 'output', id }), [open])
  // the output whose tab is in front, for the Outputs list's mark and a located passage
  const selectedOutput = activeKey?.startsWith('output:') ? activeKey.slice('output:'.length) : null
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
  // an unread source counts: an output reads it first
  const hasReadySource = uploads?.some((s) => (s.status === 'ready' || s.status === 'added') && !excluded.has(s.id)) ?? false
  const selectedSources = uploads?.filter((s) => !excluded.has(s.id)) ?? []
  const webPages = selectedSources.filter((s) => s.kind === 'url' && s.status !== 'added')
  const unreadSelected = selectedSources.filter((s) => s.status === 'added').length
  /** turns a source off by its library id (one rag reported it cannot read) */
  const deselect = (libraryId: string) => {
    const s = uploads?.find((x) => (x.library_id ?? x.id) === libraryId)
    if (s) changeExcluded(new Set(excluded).add(s.id))
  }
  // viewer/chat split, remembered per browser; full view hides the chat behind a toggle
  const [ratio, setRatio] = useState(() => readRatio(browserStorage()))
  const [fullView, setFullView] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const rightColumn = useRef<HTMLDivElement>(null)
  // the left column's width (sources, formats, outputs), remembered per browser
  const [leftWidth, setLeftWidth] = useState(() => readWidth(browserStorage(), LEFT_WIDTH.key, LEFT_WIDTH.min, LEFT_WIDTH.max))
  // the heights of Sources and Output format in the left column, per user in this browser
  const userId = useMe().me?.id ?? null
  const [leftSizes, setLeftSizes] = useState(() => readLeftSizes(browserStorage(), userId))
  // the user can arrive after the first render: their sizes then
  const [sizesFor, setSizesFor] = useState(userId)
  if (sizesFor !== userId) {
    setSizesFor(userId)
    setLeftSizes(readLeftSizes(browserStorage(), userId))
  }
  const leftColumn = useRef<HTMLDivElement>(null)
  /** an area's height now, dragged or as the stylesheet lays it out */
  const heightOf = (area: 'sources' | 'tiles') => leftSizes[area] ?? leftColumn.current?.querySelector<HTMLElement>(`:scope > .${area}`)?.getBoundingClientRect().height ?? 0
  const clampArea = (area: 'sources' | 'tiles') => (px: number) =>
    clampHeight(px, area, maxHeight(leftColumn.current?.getBoundingClientRect().height ?? 0, heightOf(area === 'sources' ? 'tiles' : 'sources'), area))
  const sizeArea = (area: 'sources' | 'tiles', px: number | null, remember: boolean) => {
    const next = { ...leftSizes, [area]: px }
    setLeftSizes(next)
    if (remember) writeLeftSizes(browserStorage(), userId, next)
  }
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
    // a deleted output's tab goes; the document the library asked for opens
    setTabs((prev) => dropMissing(prev, 'output', new Set(list.map((o) => o.id))))
    const wanted = requested.current
    requested.current = null
    if (wanted && list.some((o) => o.id === wanted)) openOutput(wanted)
  }, [notebookId, openOutput])

  useEffect(() => {
    void run(reloadOutputs)
  }, [reloadOutputs, run])

  const pending = outputs.some((o) => o.status === 'processing' || o.status === 'waiting')
  // outputs being made are paid work: the balance follows while they run and when one ends
  useBalanceActivity(pending)
  const lastOutputs = useRef(outputs)
  useEffect(() => {
    lastOutputs.current = outputs
  }, [outputs])
  useEffect(() => {
    if (!pending) return
    const t = setInterval(() => {
      rag.listOutputs(notebookId).then(
        (list) => {
          if (outputsFinished(lastOutputs.current, list)) requestBalanceRefresh()
          setOutputs(list)
        },
        () => {
          // a failed poll is retried on the next tick; user actions surface errors through run()
        },
      )
    }, OUTPUT_POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [pending, notebookId])

  // a starter copy's outputs arrive a moment after the notebook; asked again until they do
  const awaitsStarter = outputsLoaded && awaitsStarterOutputs(uploads, outputs)
  useEffect(() => {
    if (!awaitsStarter) return
    return pollStarterOutputs(() => rag.listOutputs(notebookId), setOutputs)
  }, [awaitsStarter, notebookId])

  function removeOutput(id: string) {
    setOutputs((prev) => prev.filter((x) => x.id !== id))
    closeTab(tabKey({ type: 'output', id }))
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

  async function createOutput(kind: OutputKind, options: OutputOptions, urlRefresh: string[] = []) {
    const created = await run(() => rag.createOutput(notebookId, kind, options, picked.sourceIds, urlRefresh))
    if (created) {
      setOutputs((prev) => [created, ...prev])
      openOutput(created.id)
      // unread sources start reading, pages may be fetched again: the list follows
      setSourcesVersion((v) => v + 1)
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
          openOutput(match.id)
          document.getElementById(`output-${match.id}`)?.scrollIntoView({ block: 'nearest' })
          return
        }
        // a document added from the library is listed among the sources
      }
      document.getElementById(`source-${c.source_id}`)?.scrollIntoView({ block: 'nearest' })
    },
    [outputs, openOutput],
  )

  /** A plan in the chat added a source or made an output: both lists reload. */
  const planWork = useCallback(() => {
    setSourcesVersion((v) => v + 1)
    void reloadOutputs().catch(() => {
      // the outputs' own poll or the next action shows them
    })
  }, [reloadOutputs])

  /** "Open document" on a citation into a generated document: that
   *  document's tab, and a request for the viewer to show the passage. An
   *  upload's "open in source" opens its source tab at the cited page and
   *  chunk, and highlights it in the list. */
  const [locate, setLocate] = useState<LocateRequest | null>(null)
  function openSource(c: Citation) {
    if (c.source_kind !== 'generated') {
      const src = uploads?.find((s) => s.id === c.source_id)
      open({ type: 'source', id: c.source_id, page: c.page, chunkId: c.chunk_id, chunkIndex: c.chunk_index ?? null, url: src ? tabUrl(src) : null, urlAt: Date.now() })
      onCitation(c)
      return
    }
    const match = outputs.find((o) => o.source_id === c.source_id)
    if (!match) {
      // made in another notebook and added from the library: shown in the sources list
      onCitation(c)
      return
    }
    openOutput(match.id)
    setLocate((prev) => ({ outputId: match.id, text: c.quote, nonce: (prev?.nonce ?? 0) + 1 }))
  }

  // the browser tab: the document in front, then the notebook
  const frontOutput = selectedOutput ? outputs.find((o) => o.id === selectedOutput) : undefined
  const frontSource = activeKey?.startsWith('source:') ? uploads?.find((x) => `source:${x.id}` === activeKey) : undefined
  useDocumentTitle(docTitle(frontOutput ? frontOutput.title || formFor(frontOutput.kind).label : frontSource?.name, notebookTitle))
  const sourceLink = useCallback((id: string, page: number | null) => citationTarget(uploads?.find((s) => s.id === id), page), [uploads])
  const sourceInfo = useCallback((id: string) => uploads?.find((s) => s.id === id), [uploads])

  return (
    <SourceLinks.Provider value={sourceLink}>
      <SourceInfo.Provider value={sourceInfo}>
      <div
        ref={columnsRef}
        className={['columns', fullView ? 'full' : '', fullView && chatOpen ? 'chat-open' : ''].join(' ').trim()}
        style={leftWidth === null ? undefined : ({ '--left-w': `${leftWidth}px` } as CSSProperties)}
      >
        <div
          ref={leftColumn}
          className={['column left no-print', leftSizes.sources !== null ? 'sized-sources' : '', leftSizes.tiles !== null ? 'sized-tiles' : ''].join(' ').trim()}
          style={
            {
              ...(leftSizes.sources !== null ? { '--sources-h': `${leftSizes.sources}px` } : {}),
              ...(leftSizes.tiles !== null ? { '--tiles-h': `${leftSizes.tiles}px` } : {}),
            } as CSSProperties
          }
        >
          <SourcesPane
            notebookId={notebookId}
            highlightedSourceId={highlight}
            version={sourcesVersion}
            onAdd={() => onWizard(true)}
            excluded={excluded}
            onToggle={(id) => changeExcluded(toggled(excluded, id))}
            onAll={(on) => changeExcluded(on ? new Set() : new Set(uploads?.map((s) => s.id) ?? []))}
            ownGenerated={ownGenerated}
            onSourcesChange={(list) => {
              setUploads(list)
              // a removed source's tab goes; an open one keeps its address unless it runs out
              const now = Date.now()
              setTabs((prev) => {
                const kept = dropMissing(prev, 'source', new Set(list.map((s) => s.id)))
                const listed = (id: string) => {
                  const found = list.find((s) => s.id === id)
                  return found ? tabUrl(found) : null
                }
                const next = kept.map((x) => heldUrl(x, listed(x.id), now))
                return next.every((x, i) => x === kept[i]) ? kept : next
              })
            }}
            onOpen={(s) => open({ type: 'source', id: s.id, url: tabUrl(s), urlAt: Date.now() })}
          />
          <RowDivider
            label={t('ws.resizeSources')}
            height={leftSizes.sources}
            clamp={clampArea('sources')}
            onChange={(px) => sizeArea('sources', px, false)}
            onCommit={(px) => sizeArea('sources', px, true)}
            onReset={() => sizeArea('sources', null, true)}
          />
          <OutputTiles
            notebookId={notebookId}
            selected={format}
            hasReadySource={hasReadySource}
            noneSelected={picked.total > 0 && picked.selected === 0}
            busy={busy}
            onSelect={setFormat}
            onCreate={(k, o, refresh) => void createOutput(k, o, refresh)}
            sourceIds={picked.sourceIds}
            webPages={webPages}
            onDeselect={deselect}
          />
          <RowDivider
            label={t('ws.resizeFormats')}
            height={leftSizes.tiles}
            clamp={clampArea('tiles')}
            onChange={(px) => sizeArea('tiles', px, false)}
            onCommit={(px) => sizeArea('tiles', px, true)}
            onReset={() => sizeArea('tiles', null, true)}
          />
          <OutputsPane outputs={outputs} sources={uploads} selectedId={selectedOutput} onOpen={openOutput} onDelete={(o) => void deleteOutput(o)} onRename={(o, title) => void renameOutput(o, title)} />
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
            tabs={tabs}
            activeKey={activeKey}
            onActivate={setActiveKey}
            onClose={closeTab}
            onCloseTabs={closeTabs}
          onSourcesChanged={() => setSourcesVersion((v) => v + 1)}
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
              webPages={webPages}
              unreadSelected={unreadSelected}
              onDeselect={deselect}
              onClearScope={() => setScope(null)}
              onCitationSelected={onCitation}
              onOpenSource={openSource}
              onOpenTab={(target) => {
                const src = target.type === 'source' ? uploads?.find((s) => s.id === target.id) : undefined
                open({ type: target.type, id: target.id, ...(src ? { url: tabUrl(src), urlAt: Date.now() } : {}) })
              }}
              onWork={planWork}
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
          <Wizard notebookId={notebookId} onAdded={() => setSourcesVersion((v) => v + 1)} onClose={() => onWizard(false)} />
        )}
      </div>
      {/* not over the add-sources dialog */}
      {!wizard && <Tour />}
      </SourceInfo.Provider>
    </SourceLinks.Provider>
  )
}
