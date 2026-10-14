import type { CreditEntry } from '../api/types'
import { t } from '../i18n'
import { actionLabel } from './prices'

/** What a credit entry was, as a line: "Report in notebook test1",
 *  "Source linux_vi.pdf processed", "Question in notebook Fog", "Voucher
 *  redeemed". A deleted notebook, output or source is named as deleted.
 *  `open` says what the line links to while it exists. Pure, so it is
 *  tested. */
export function creditLine(e: CreditEntry): { text: string; open: { notebookId: string; outputId?: string } | null } {
  if (e.type === 'voucher') return { text: t('credit.voucher'), open: null }
  if (e.type === 'grant') return { text: t('credit.grant'), open: null }
  const key = e.label_key ?? e.action ?? ''
  const what = actionLabel(key)
  const nb = e.notebook ? (e.notebook.title ?? t('credit.deletedNotebook')) : null
  let text: string
  if (key.startsWith('source:')) text = t('credit.source', { name: e.source ? (e.source.title ?? t('credit.deletedSource')) : what })
  else if (key.startsWith('output:')) text = nb ? t('credit.outputIn', { what: e.output?.title || what, notebook: nb }) : (e.output?.title ?? what)
  else if (key.startsWith('judge')) text = e.output ? t('credit.judgeOn', { what, output: e.output.title ?? t('credit.deletedOutput') }) : what
  else text = nb ? t('credit.in', { what, notebook: nb }) : what
  const notebookId = e.notebook?.title != null ? e.notebook.id : null
  const outputId = e.output?.title != null ? e.output.id : undefined
  return { text, open: notebookId ? { notebookId, ...(outputId ? { outputId } : {}) } : null }
}
