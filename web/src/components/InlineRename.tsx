import { useState } from 'react'

interface Props {
  value: string
  /** what is being renamed, for screen readers */
  label: string
  maxLength: number
  className?: string
  /** the new title, or null when nothing should be saved (empty, unchanged) */
  onCommit: (draft: string) => void
  onCancel: () => void
}

/** The field a double-click (or F2) turns a title into, as on the chat
 *  tabs: Enter or leaving it saves, Escape cancels; its keys stay in it. */
export function InlineRename({ value, label, maxLength, className = 'tab-edit', onCommit, onCancel }: Props) {
  const [draft, setDraft] = useState(value)
  const [done, setDone] = useState(false)
  const finish = (save: boolean) => {
    if (done) return
    setDone(true)
    if (save) onCommit(draft)
    else onCancel()
  }
  return (
    <input
      className={className}
      aria-label={label}
      value={draft}
      size={Math.max(Math.min(draft.length, 60), 4)}
      maxLength={maxLength}
      autoFocus
      onFocus={(e) => e.currentTarget.select()}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => finish(true)}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation()
        if (e.key === 'Enter') finish(true)
        if (e.key === 'Escape') finish(false)
      }}
    />
  )
}
