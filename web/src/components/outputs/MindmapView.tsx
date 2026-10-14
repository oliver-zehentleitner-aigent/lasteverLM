import { useEffect, useRef, type KeyboardEvent } from 'react'
import type { Markmap } from 'markmap-view'
import type { MindmapContent } from '../../api/types'
import { t } from '../../i18n'
import { bestMatchIndex, firstLine, type LocateRequest } from '../../lib/locate'
import { mapAction } from '../../lib/mapKeys'
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
 *  page all have it. */
export function MindmapView({ content, locate }: { content: MindmapContent; locate?: LocateRequest | null }) {
  const box = useRef<HTMLDivElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const error = useRef<HTMLParagraphElement>(null)
  const map = useRef<Markmap | null>(null)
  const cite = useCite()
  const known = cite?.known

  useEffect(() => {
    let destroy: (() => void) | undefined
    let cancelled = false
    Promise.all([import('markmap-lib'), import('markmap-view')])
      .then(([{ Transformer }, { Markmap }]) => {
        if (cancelled || !svg.current) return
        // with provenance each node carries its markers and badge, as HTML in its label
        const { root } = new Transformer().transform(toMarkdown(content.root, 0, known ? (n) => claimHtml(n, known) : undefined))
        // the labels are the model's text and markmap renders them as HTML
        const clean = cleanTree(root, sanitizeHtml)
        const mm = Markmap.create(svg.current, { autoFit: true }, clean)
        map.current = mm
        let frame = 0
        const observer = new ResizeObserver(() => {
          cancelAnimationFrame(frame)
          frame = requestAnimationFrame(() => void mm.fit())
        })
        if (box.current) observer.observe(box.current)
        destroy = () => {
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
  }, [content, known])

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
