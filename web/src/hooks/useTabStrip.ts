import { useEffect, useRef, type KeyboardEvent, type WheelEvent } from 'react'
import { tabForKey } from '../lib/tabs'

/** A horizontally scrolling tab bar: the active tab is scrolled into view,
 *  a vertical mouse wheel scrolls sideways, and arrows, Home and End move
 *  between tabs. Each tab needs `data-tab-id`. */
export function useTabStrip(ids: readonly string[], active: string | null, onSelect: (id: string) => void) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!active || !ref.current) return
    const el = ref.current.querySelector<HTMLElement>(`[data-tab-id="${CSS.escape(active)}"]`)
    el?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [active])

  function onWheel(e: WheelEvent<HTMLDivElement>) {
    const el = e.currentTarget
    if (el.scrollWidth <= el.clientWidth || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
    el.scrollLeft += e.deltaY
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const next = tabForKey(ids, active, e.key)
    if (!next) return
    e.preventDefault()
    onSelect(next)
    ref.current?.querySelector<HTMLElement>(`[data-tab-id="${CSS.escape(next)}"]`)?.focus()
  }

  return { ref, onWheel, onKeyDown }
}
