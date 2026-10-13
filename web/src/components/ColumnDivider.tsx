import { useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { clampWidth } from '../lib/layout'

interface Props {
  label: string
  /** the column's current width; null while it has the stylesheet default */
  width: number | null
  min: number
  /** the largest width allowed right now (the other column keeps its minimum) */
  max: () => number
  /** the left edge the width is measured from */
  origin: () => number
  onChange: (px: number) => void
  /** drag or key finished: the moment to remember the width */
  onCommit: (px: number) => void
  onReset: () => void
}

const STEP = 16

/** A vertical bar between two columns: drag to resize the column on its
 *  left, arrow keys when focused, double-click (or Home) for the default. */
export function ColumnDivider({ label, width, min, max, origin, onChange, onCommit, onReset }: Props) {
  const dragging = useRef(false)
  const last = useRef<number | null>(null)

  const measured = (el: HTMLElement) => width ?? (el.previousElementSibling as HTMLElement | null)?.getBoundingClientRect().width ?? min

  function move(e: PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return
    const px = clampWidth(e.clientX - origin(), min, max())
    last.current = px
    onChange(px)
  }

  function end(e: PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return
    dragging.current = false
    e.currentTarget.releasePointerCapture(e.pointerId)
    if (last.current !== null) onCommit(last.current)
  }

  function key(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Home') {
      e.preventDefault()
      onReset()
      return
    }
    const delta = e.key === 'ArrowLeft' ? -STEP : e.key === 'ArrowRight' ? STEP : 0
    if (!delta) return
    e.preventDefault()
    const px = clampWidth(measured(e.currentTarget) + delta, min, max())
    onChange(px)
    onCommit(px)
  }

  return (
    <div
      className="vdivider no-print"
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width ?? undefined}
      aria-valuemin={min}
      tabIndex={0}
      title="Drag to resize, double-click to reset"
      onPointerDown={(e) => {
        dragging.current = true
        last.current = null
        e.currentTarget.setPointerCapture(e.pointerId)
      }}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      onDoubleClick={onReset}
      onKeyDown={key}
    />
  )
}
