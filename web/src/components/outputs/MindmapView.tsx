import { useEffect, useRef, type KeyboardEvent } from 'react'
import type { Markmap } from 'markmap-view'
import type { MindmapContent } from '../../api/types'
import { t } from '../../i18n'
import { mapAction } from '../../lib/mapKeys'
import { toMarkdown } from '../../lib/mindmap'

/** Renders the tree with markmap, loaded on demand so the main bundle stays
 *  small; nothing else in the app needs d3. The content is converted to the
 *  Markdown list markmap expects. The SVG fills its container, and markmap
 *  keeps the geometry it measured, so every size change of the container
 *  (full view, the divider, the window) re-fits the map on the next frame.
 *  A small control bar on the map (fit, zoom in, zoom out) and the keys 0,
 *  + and − on the focused map bring it back after panning and zooming; it
 *  sits on the map itself, so the viewer, the full view and the shared
 *  page all have it. */
export function MindmapView({ content }: { content: MindmapContent }) {
  const box = useRef<HTMLDivElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const error = useRef<HTMLParagraphElement>(null)
  const map = useRef<Markmap | null>(null)

  useEffect(() => {
    let destroy: (() => void) | undefined
    let cancelled = false
    Promise.all([import('markmap-lib'), import('markmap-view')])
      .then(([{ Transformer }, { Markmap }]) => {
        if (cancelled || !svg.current) return
        const { root } = new Transformer().transform(toMarkdown(content.root))
        const mm = Markmap.create(svg.current, { autoFit: true }, root)
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
  }, [content])

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
    <div className="mindmap" ref={box}>
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
