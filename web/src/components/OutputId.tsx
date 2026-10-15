import { useRef } from 'react'
import { t } from '../i18n'
import { shortId } from '../lib/outputId'
import { CopyButton } from './CopyButton'

/** "ID 3f9c21ab ⧉": an output's short ID, the button copying the full one
 *  (where the clipboard is unavailable it selects the full ID, kept in a
 *  visually hidden span, for Ctrl+C). `full` shows the whole ID. */
export function OutputId({ id, full = false }: { id: string; full?: boolean }) {
  const whole = useRef<HTMLSpanElement>(null)
  return (
    <span className="output-id muted small" title={t('outputId.title', { id })}>
      {!full && `${t('outputId.label')} `}
      <code>{full ? id : shortId(id)}</code>
      <span ref={whole} className="sr-only">
        {id}
      </span>{' '}
      <CopyButton text={id} target={whole} label="⧉" ariaLabel={t('outputId.copy')} />
    </span>
  )
}
