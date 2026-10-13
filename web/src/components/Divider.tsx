import { useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { DEFAULT_VIEWER_RATIO, MAX_VIEWER_RATIO, MIN_VIEWER_RATIO, clampRatio, ratioFromPointer } from '../lib/layout'

interface Props {
  ratio: number
  /** the column the ratio is measured against */
  container: () => HTMLElement | null
  onChange: (ratio: number) => void
  /** drag or key finished: the moment to remember the ratio */
  onCommit: (ratio: number) => void
  onReset: () => void
}

const STEP = 0.05

/** The horizontal bar between viewer and chat. Drag to move it, arrow keys
 *  when focused, double-click (or Home) for the default split. */
export function Divider({ ratio, container, onChange, onCommit, onReset }: Props) {
  const dragging = useRef(false)

  function move(e: PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return
    const box = container()?.getBoundingClientRect()
    if (box) onChange(ratioFromPointer(e.clientY, box.top, box.height))
  }

  function end(e: PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return
    dragging.current = false
    e.currentTarget.releasePointerCapture(e.pointerId)
    onCommit(ratio)
  }

  function key(e: KeyboardEvent<HTMLDivElement>) {
    const next =
      e.key === 'ArrowUp' ? ratio - STEP : e.key === 'ArrowDown' ? ratio + STEP : e.key === 'Home' ? DEFAULT_VIEWER_RATIO : null
    if (next === null) return
    e.preventDefault()
    if (e.key === 'Home') {
      onReset()
      return
    }
    const r = clampRatio(next)
    onChange(r)
    onCommit(r)
  }

  return (
    <div
      className="divider no-print"
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize document and chat"
      aria-valuemin={MIN_VIEWER_RATIO * 100}
      aria-valuemax={MAX_VIEWER_RATIO * 100}
      aria-valuenow={Math.round(ratio * 100)}
      tabIndex={0}
      title="Drag to resize, double-click to reset"
      onPointerDown={(e) => {
        dragging.current = true
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
