import type { Citation } from '../api/types'
import { t } from '../i18n'

/** An answer for the clipboard: its text with the [n] markers as they
 *  stand, then the cited passages, one per marker, with source and page.
 *  Pure, so it is tested. */
export function answerForClipboard(answer: string, citations: readonly Citation[] | null | undefined): string {
  if (!citations || citations.length === 0) return answer.trim()
  const lines = [...citations]
    .sort((a, b) => a.n - b.n)
    .map((c) => `[${c.n}] ${c.source_name}${c.page != null ? `, ${t('chat.page', { page: c.page })}` : ''}: "${c.quote.trim().replace(/\s+/g, ' ')}"`)
  return `${answer.trim()}\n\n${t('chat.copySources')}\n${lines.join('\n')}`
}
