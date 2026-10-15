import type { Claim, JudgeCounts, JudgeNote, Provenance } from '../api/types'
import type { EstimateState } from '../hooks/useEstimate'
import { t, tn } from '../i18n'
import { priceLabel } from './estimate'

/** The judge's verdicts as the views show them. Pure, so it is tested. */

/** Where the word check and the judge read a claim differently: the check
 *  backed it and the judge did not, or the other way round. A claim the
 *  check could not measure (another language) is no disagreement. */
export function disagrees(c: Claim): boolean {
  if (!c.judge?.verdict || !c.support || c.support === 'unverified') return false
  return (c.support === 'supported') !== (c.judge.verdict === 'supported')
}

/** "Judge (medium, glm-4.6): 7 of 9 passed after 2 rounds" for a judging
 *  while it was made; "Judge (low, …): 5 of 6 supported" for the latest
 *  one asked for afterwards; null without either. */
export function judgeHead(p: Pick<Provenance, 'judge' | 'judgements'> | null | undefined): string | null {
  const run = p?.judge
  // verification standard: one pass over what the word check doubted
  if (run?.mode === 'doubted' && (run.judged ?? 0) > 0) {
    return t('judge.headDoubted', { level: t(`judge.level.${run.level}`).toLowerCase(), model: run.model, judged: run.judged ?? 0, passed: run.verdicts?.supported ?? 0 })
  }
  if (run?.rounds && run.rounds.length > 0) {
    const first = run.rounds[0]
    const last = run.rounds[run.rounds.length - 1]
    return t('judge.headRun', {
      level: t(`judge.level.${run.level}`).toLowerCase(),
      model: run.model,
      passed: last.verdicts.supported ?? 0,
      total: first.judged,
      rounds: tn('judge.rounds', run.rounds.length),
    })
  }
  const latest = p?.judgements?.[p.judgements.length - 1]
  if (latest) {
    const total = Object.values(latest.verdicts).reduce((a, b) => a + (b ?? 0), 0)
    return t('judge.headLater', { level: t(`judge.level.${latest.level}`).toLowerCase(), model: latest.model, passed: latest.verdicts.supported ?? 0, total })
  }
  return null
}

/** A judged claim's verdict as a CSS and message suffix: no verdict is
 *  "no_usable_answer", as the counts name it. */
export function verdictKey(j: Pick<JudgeNote, 'verdict'>): keyof JudgeCounts {
  return j.verdict ?? 'no_usable_answer'
}

/** The counts of a round or a judging, as "supported 5 · contradicted 1". */
export function verdictCounts(v: JudgeCounts): string {
  return (['supported', 'contradicted', 'not_in_source', 'no_usable_answer'] as const)
    .filter((k) => (v[k] ?? 0) > 0)
    .map((k) => `${t(`judge.verdict.${k}`)} ${v[k]}`)
    .join(' · ')
}

/** The badge's text and its tooltip (the judge's reason). */
export function judgeBadge(c: Claim): { verdict: keyof JudgeCounts; label: string; title: string; disagree: boolean } | null {
  if (!c.judge) return null
  const d = disagrees(c)
  // the word check's result moves into the judge's tooltip: its badge is not shown beside a verdict
  const word = c.judge.verdict && c.support ? `\n${t(`wordCheck.${c.support}`)}` : ''
  const title = (d ? `${c.judge.reason} — ${t('judge.disagreeTitle')}` : c.judge.reason) + word
  const verdict = verdictKey(c.judge)
  return { verdict, label: t(`judge.verdict.${verdict}`), title, disagree: d }
}

/** The level "Have it judged" is priced at: the one Check with a judge starts at. */
export const JUDGE_ASK_LEVEL = 'medium'

/** "Have it judged · €0.02"; the bare action while the price loads or
 *  when it is unavailable (Check with a judge then says why). */
export function judgeAskLabel(price: EstimateState): string {
  return price && 'estimate' in price ? `${t('judge.ask')} · ${priceLabel(price.estimate)}` : t('judge.ask')
}
