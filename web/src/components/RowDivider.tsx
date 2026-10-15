import { useRef, type KeyboardEvent, type PointerEvent } from 'react'
import { t } from '../i18n'

interface Props {
  label: string
  /** the area above's height; null while it has the stylesheet default */
  height: number | null
  /** the height allowed for a value, from the area's minimum and what the others keep */
  clamp: (px: number) => number
  onChange: (px: number) => void
  /** drag or key finished: the moment to remember the height */
  onCommit: (px: number) => void
  onReset: () => void
}

const STEP = 16

/** A horizontal bar between two areas of a column: drag to resize the area
 *  above it, arrow keys when focused, double-click (or Home) for the
 *  default. Hidden in the phone layout, where the column just scrolls. */
export function RowDivider({ label, height, clamp, onChange, onCommit, onReset }: Props) {
  const dragging = useRef(false)
  const last = useRef<number | null>(null)

  const above = (el: HTMLElement) => el.previousElementSibling as HTMLElement | null
  const measured = (el: HTMLElement) => height ?? above(el)?.getBoundingClientRect().height ?? 0

  function move(e: PointerEvent<HTMLDivElement>) {
    if (!dragging.current) return
    const top = above(e.currentTarget)?.getBoundingClientRect().top
    if (top === undefined) return
    const px = clamp(e.clientY - top)
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
    const delta = e.key === 'ArrowUp' ? -STEP : e.key === 'ArrowDown' ? STEP : 0
    if (!delta) return
    e.preventDefault()
    const px = clamp(measured(e.currentTarget) + delta)
    onChange(px)
    onCommit(px)
  }

  return (
    <div
      className="row-divider no-print"
      role="separator"
      aria-orientation="horizontal"
      aria-label={label}
      aria-valuenow={height ?? undefined}
      tabIndex={0}
      title={t('divider.hint')}
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
