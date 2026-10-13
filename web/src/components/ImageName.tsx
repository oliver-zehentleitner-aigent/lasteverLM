import { useEffect, useRef, useState, type MouseEvent, type PointerEvent } from 'react'
import { createPortal } from 'react-dom'
import { previewPosition } from '../lib/preview'

interface Props {
  /** presigned for an hour; absent for entries without a picture */
  previewUrl?: string | null
  /** the text shown next to the thumbnail */
  label: string
  /** tooltip and alt text, e.g. the full file name */
  title: string
}

const SIZE = 320

/** A name with a small square thumbnail in front when the entry is an
 *  image. Hovering the thumbnail or the name, or focusing the thumbnail,
 *  shows a medium preview that stays inside the viewport; Esc or leaving
 *  hides it. On touch a tap on the thumbnail opens it (and does not toggle
 *  a surrounding checkbox row), a tap elsewhere closes it. */
export function ImageName({ previewUrl, label, title }: Props) {
  const thumb = useRef<HTMLImageElement>(null)
  const touched = useRef(false)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)

  function show() {
    const r = thumb.current?.getBoundingClientRect()
    if (r) setPos(previewPosition(r, { width: window.innerWidth, height: window.innerHeight }, { width: SIZE, height: SIZE }))
  }
  const hide = () => setPos(null)

  useEffect(() => {
    if (!pos) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && hide()
    const onOutside = (e: globalThis.PointerEvent) => e.target !== thumb.current && hide()
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onOutside)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onOutside)
    }
  }, [pos])

  if (!previewUrl) return <span className="image-name-text" title={title}>{label}</span>

  return (
    <span className="image-name" onMouseEnter={show} onMouseLeave={hide}>
      <img
        ref={thumb}
        className="thumb"
        src={previewUrl}
        alt={title}
        loading="lazy"
        decoding="async"
        tabIndex={0}
        onFocus={show}
        onBlur={hide}
        onPointerDown={(e: PointerEvent<HTMLImageElement>) => {
          touched.current = e.pointerType === 'touch'
        }}
        onClick={(e: MouseEvent<HTMLImageElement>) => {
          if (!touched.current) return
          // a tap previews; it must not toggle the row's checkbox
          e.preventDefault()
          e.stopPropagation()
          if (pos) hide()
          else show()
        }}
      />
      <span className="image-name-text" title={title}>
        {label}
      </span>
      {pos &&
        createPortal(
          <div className="image-preview" style={{ left: pos.left, top: pos.top }} aria-hidden="true">
            <img src={previewUrl} alt="" />
          </div>,
          document.body,
        )}
    </span>
  )
}
