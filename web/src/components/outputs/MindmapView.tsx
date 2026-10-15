import { useEffect, useMemo, useRef, type KeyboardEvent } from 'react'
import type { Markmap } from 'markmap-view'
import type { MindmapContent, MindmapNode } from '../../api/types'
import { t } from '../../i18n'
import { bestMatchIndex, firstLine, type LocateRequest } from '../../lib/locate'
import { mapAction, wheelAction } from '../../lib/mapKeys'
import { cleanTree, toMarkdown } from '../../lib/mindmap'
import { sanitizeHtml } from '../../lib/sanitize'
import { claimHtml } from '../../lib/outputProvenance'
import { useCite } from '../../hooks/useCite'

/** Renders the tree with markmap, loaded on demand so the main bundle stays
 *  small; nothing else in the app needs d3. The content is converted to the
 *  Markdown list markmap expects. The SVG fills its container, and markmap
 *  keeps the geometry it measured, so every size change of the container
 *  (full view, the divider, the window) re-fits the map on the next frame.
 *  A small control bar on the map (fit, zoom in, zoom out) and the keys 0,
 *  + and − on the focused map bring it back after panning and zooming; it
 *  sits on the map itself, so the viewer, the full view and the shared
 *  page all have it. Labels wrap at LABEL_MAX_WIDTH: unwrapped, one long
 *  label made the map so wide that fitting shrank it to an unreadable
 *  sliver. The map is built again only when its content changes, not
 *  when a poll hands over an equal output, and it is fitted once it is
 *  drawn and only while the pane has a size. */
export function MindmapView({ content, locate }: { content: MindmapContent; locate?: LocateRequest | null }) {
  const box = useRef<HTMLDivElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const error = useRef<HTMLParagraphElement>(null)
  const map = useRef<Markmap | null>(null)
  const cite = useCite()
  const known = cite?.known
  // equal content and markers keep the map: a poll's new objects must not rebuild it
  const contentKey = useMemo(() => JSON.stringify(content.root), [content])
  const knownKey = known ? [...known].sort((a, b) => a - b).join(',') : ''
  const latest = useRef({ content, known })
  useEffect(() => {
    latest.current = { content, known }
  }, [content, known])

  useEffect(() => {
    let destroy: (() => void) | undefined
    let cancelled = false
    Promise.all([import('markmap-lib'), import('markmap-view')])
      .then(([{ Transformer }, { Markmap }]) => {
        if (cancelled || !svg.current) return
        const { content, known } = latest.current
        // with provenance each node carries its markers and badge, as HTML in its label
        const order = nodeOrder(content.root)
        const { root } = new Transformer().transform(toMarkdown(content.root, 0, known ? (n) => claimHtml(n, known, order.indexOf(n)) : undefined))
        // the labels are the model's text and markmap renders them as HTML
        const clean = cleanTree(root, sanitizeHtml)
        const el = svg.current
        // the wheel scrolls (Shift: sideways) and Ctrl/Cmd+wheel zooms; markmap's d3 zoom
        // keeps Ctrl+wheel, which is also how a trackpad's pinch arrives
        const mm = Markmap.create(el, { autoFit: false, maxWidth: LABEL_MAX_WIDTH, scrollForPan: true, pan: false })
        map.current = mm
        const onWheel = (e: WheelEvent) => {
          const action = wheelAction(e)
          if (action.kind === 'zoom-native') return
          e.preventDefault()
          if (action.kind === 'zoom') void mm.rescale(action.by)
          else mm.handlePan({ deltaX: action.dx, deltaY: action.dy, preventDefault: () => {} } as unknown as WheelEvent)
        }
        el.addEventListener('wheel', onWheel, { passive: false })
        // fitting an SVG without a size scales the map to nothing
        const sized = () => {
          const r = el.getBoundingClientRect()
          return r.width > 0 && r.height > 0
        }
        let drawn = false
        let frame = 0
        const refit = () => {
          cancelAnimationFrame(frame)
          frame = requestAnimationFrame(() => {
            if (drawn && sized()) void mm.fit()
          })
        }
        // the first fit once the nodes are drawn and measured, then on every size change
        void mm.setData(clean).then(() => {
          if (cancelled) return
          drawn = true
          refit()
        })
        const observer = new ResizeObserver(refit)
        if (box.current) observer.observe(box.current)
        destroy = () => {
          el.removeEventListener('wheel', onWheel)
          observer.disconnect()
          cancelAnimationFrame(frame)
          map.current = null
          mm.destroy()
        }
      })
      .catch((e: unknown) => {
        if (error.current) error.current.textContent = e instanceof Error ? e.message : String(e)
      })
    return () => {
      cancelled = true
      destroy?.()
    }
  }, [contentKey, knownKey])

  // "open document" on a citation: fit the map, then flash the node whose
  // label matches the chunk's first line (the outline starts at its node)
  useEffect(() => {
    if (!locate) return
    const mm = map.current
    if (!mm) return
    let timer = 0
    void mm.fit().then(() => {
      timer = window.setTimeout(() => {
        const nodes = [...(svg.current?.querySelectorAll<HTMLElement>('.markmap-foreign') ?? [])]
        const i = bestMatchIndex(
          nodes.map((n) => n.textContent ?? ''),
          firstLine(locate.text),
        )
        // the label is a div inside markmap's foreignObject, which itself paints nothing
        const label = i >= 0 ? ((nodes[i].firstElementChild as HTMLElement | null) ?? nodes[i]) : null
        if (label) {
          label.classList.remove('flash')
          void label.offsetWidth
          label.classList.add('flash')
          window.setTimeout(() => label.classList.remove('flash'), 1800)
        }
      }, 50)
    })
    return () => window.clearTimeout(timer)
  }, [locate])

  const fit = () => void map.current?.fit()
  const zoom = (by: number) => void map.current?.rescale(by)

  function onKey(e: KeyboardEvent<SVGSVGElement>) {
    const action = mapAction(e.key)
    if (!action) return
    e.preventDefault()
    if (action.kind === 'fit') fit()
    else zoom(action.by)
  }

  return (
    // a marker in a node's label shows its passage; markmap folds on the circle, not the label
    <div
      className="mindmap"
      ref={box}
      onClick={(e) => {
        const judge = (e.target as HTMLElement).closest<HTMLButtonElement>('button.judge[data-u]')
        if (judge && cite) {
          e.stopPropagation()
          const node = nodeOrder(content.root)[Number(judge.dataset.u)]
          const n = node?.refs?.find((r) => cite.known.has(r))
          if (node?.judge && n !== undefined) cite.cite(n, node.label, node.judge)
          return
        }
        const button = (e.target as HTMLElement).closest<HTMLButtonElement>('button.cite[data-n]')
        if (!button || !cite) return
        e.stopPropagation()
        cite.cite(Number(button.dataset.n), button.closest('.markmap-foreign')?.textContent ?? '')
      }}
    >
      <div className="map-controls no-print" role="group" aria-label={t('map.controls')}>
        <button type="button" className="secondary small" title={t('map.zoomIn')} aria-label={t('map.zoomIn')} onClick={() => zoom(1.25)}>
          +
        </button>
        <button type="button" className="secondary small" title={t('map.zoomOut')} aria-label={t('map.zoomOut')} onClick={() => zoom(0.8)}>
          −
        </button>
        <button type="button" className="secondary small" title={t('map.fit')} aria-label={t('map.fit')} onClick={fit}>
          ⤢
        </button>
      </div>
      <svg ref={svg} tabIndex={0} aria-label={t('map.label')} onKeyDown={onKey} />
      <p ref={error} className="error" />
    </div>
  )
}

/** px at which a label wraps (markmap's maxWidth) */
const LABEL_MAX_WIDTH = 280

/** The nodes in the order toMarkdown writes them, root first: a judge
 *  badge's index into this list finds its node again. */
function nodeOrder(root: MindmapNode): MindmapNode[] {
  return [root, ...(root.children ?? []).flatMap(nodeOrder)]
}
