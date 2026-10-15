import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react'

export interface MenuItem {
  label: string
  onSelect: () => void
  disabled?: boolean
}

/** A small menu that opens from a button: an optional header that is not
 *  an item, then the items. The first item takes the focus, the arrow
 *  keys, Home and End move between them, Escape and a click elsewhere
 *  close it, and a pick closes it too (Escape returns the focus to the
 *  button that opened it, through `onClose`). */
export function PopupMenu({ label, header, items, onClose, className }: { label: string; header?: ReactNode; items: MenuItem[]; onClose: () => void; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    ref.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus()
    const away = (e: Event) => {
      if (!ref.current?.contains(e.target as Node)) onClose()
    }
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [onClose])

  function key(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
      return
    }
    const moves: Record<string, (i: number, n: number) => number> = {
      ArrowDown: (i, n) => (i + 1) % n,
      ArrowUp: (i, n) => (i - 1 + n) % n,
      Home: () => 0,
      End: (_i, n) => n - 1,
    }
    const move = moves[e.key]
    if (!move) return
    e.preventDefault()
    const all = [...(ref.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [])]
    if (all.length === 0) return
    all[move(all.indexOf(document.activeElement as HTMLButtonElement), all.length)]?.focus()
  }

  return (
    <div className={['popup-menu', className].filter(Boolean).join(' ')} ref={ref} onKeyDown={key}>
      {header && <div className="popup-menu-header">{header}</div>}
      <ul role="menu" aria-label={label}>
        {items.map((it) => (
          <li key={it.label} role="none">
            <button
              type="button"
              role="menuitem"
              disabled={it.disabled}
              onClick={() => {
                onClose()
                it.onSelect()
              }}
            >
              {it.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
