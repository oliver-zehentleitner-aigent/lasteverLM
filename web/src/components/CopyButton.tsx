import { useEffect, useRef, useState, type RefObject } from 'react'
import { t } from '../i18n'

interface Props {
  text: string
  /** the element whose text is selected when the clipboard is not available */
  target: RefObject<HTMLElement | null>
  label?: string
  /** the button's name when its label is a symbol */
  ariaLabel?: string
}

/** Copies `text` with the clipboard API and says "copied" for a second.
 *  Without the API (plain http, an old browser, a denied permission) it
 *  selects the target's text instead, so Ctrl+C finishes the job. */
export function CopyButton({ text, target, label, ariaLabel }: Props) {
  const [state, setState] = useState<'idle' | 'copied' | 'selected'>('idle')
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  function flash(s: 'copied' | 'selected') {
    setState(s)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setState('idle'), s === 'copied' ? 1000 : 3000)
  }

  function selectTarget() {
    const el = target.current
    const sel = window.getSelection()
    if (!el || !sel) return
    const range = document.createRange()
    range.selectNodeContents(el)
    sel.removeAllRanges()
    sel.addRange(range)
    flash('selected')
  }

  function copy() {
    if (!navigator.clipboard?.writeText) {
      selectTarget()
      return
    }
    navigator.clipboard.writeText(text).then(() => flash('copied'), selectTarget)
  }

  return (
    <button type="button" className="link copy" onClick={copy} aria-live="polite" aria-label={state === 'idle' ? ariaLabel : undefined} title={ariaLabel}>
      {state === 'copied' ? t('copy.copied') : state === 'selected' ? t('copy.selected') : (label ?? t('copy.copy'))}
    </button>
  )
}
