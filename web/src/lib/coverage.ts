import type { Coverage } from '../api/types'
import { t } from '../i18n'

/** "4 of 5 sources used" for the head; null without a coverage or with
 *  nothing selected. Pure, so it is tested. */
export function coverageLine(c: Coverage | null | undefined): string | null {
  if (!c || c.selected <= 0) return null
  return t('coverage.line', { cited: c.cited, selected: c.selected })
}

/** The selected sources no unit cites, each with why: the generator's own
 *  sentence, or "not used, no reason given". */
export function unusedSources(c: Coverage | null | undefined): { name: string; reason: string }[] {
  return (c?.sources ?? []).filter((s) => !s.cited).map((s) => ({ name: s.name, reason: s.reason?.trim() || t('coverage.noReason') }))
}
