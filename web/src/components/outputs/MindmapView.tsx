import { useEffect, useRef } from 'react'
import type { MindmapContent } from '../../api/types'
import { toMarkdown } from '../../lib/mindmap'

/** Renders the tree with markmap, loaded on demand so the main bundle stays
 *  small; nothing else in the app needs d3. The content is converted to the
 *  Markdown list markmap expects. The SVG fills its container, and markmap
 *  keeps the geometry it measured, so every size change of the container
 *  (full view, the divider, the window) re-fits the map on the next frame. */
export function MindmapView({ content }: { content: MindmapContent }) {
  const box = useRef<HTMLDivElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const error = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    let destroy: (() => void) | undefined
    let cancelled = false
    Promise.all([import('markmap-lib'), import('markmap-view')])
      .then(([{ Transformer }, { Markmap }]) => {
        if (cancelled || !svg.current) return
        const { root } = new Transformer().transform(toMarkdown(content.root))
        const mm = Markmap.create(svg.current, { autoFit: true }, root)
        let frame = 0
        const observer = new ResizeObserver(() => {
          cancelAnimationFrame(frame)
          frame = requestAnimationFrame(() => void mm.fit())
        })
        if (box.current) observer.observe(box.current)
        destroy = () => {
          observer.disconnect()
          cancelAnimationFrame(frame)
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

  return (
    <div className="mindmap" ref={box}>
      <svg ref={svg} />
      <p ref={error} className="error" />
    </div>
  )
}
