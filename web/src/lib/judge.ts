import type { Claim, JudgeCounts, JudgeNote, JudgeVerdict, Provenance } from '../api/types'
import type { EstimateState } from '../hooks/useEstimate'
import { t, tn } from '../i18n'
import { priceLabel } from './estimate'

/** The judge's verdicts as the views show them. Pure, so it is tested. */

/** Where the word check and the judge read a claim differently: the check
 *  backed it and the judge did not, or the other way round. A claim the
 *  check could not measure (another language) is no disagreement. */
export function disagrees(c: Claim): boolean {
  if (!c.judge?.verdict || !c.support || c.support === 'unverified') return false
  return (c.support === 'supported') !== backed(c.judge.verdict)
}

/** Whether a verdict backs the claim: supported, or supported by a passage
 *  the judge added to its citations. */
export const backed = (v: JudgeVerdict | null | undefined): boolean => v === 'supported' || v === 'supported_elsewhere'

const passedOf = (v: JudgeCounts | undefined) => (v?.supported ?? 0) + (v?.supported_elsewhere ?? 0)

/** ", 3 with an added citation" after a head that counts some, else nothing. */
const addedPart = (v: JudgeCounts | undefined) => ((v?.supported_elsewhere ?? 0) > 0 ? tn('judge.withAdded', v!.supported_elsewhere!) : '')

/** "Judge (medium, glm-4.6): 7 of 9 passed after 2 rounds" for a judging
 *  while it was made; "Judge (low, …): 5 of 6 supported" for the latest
 *  one asked for afterwards; null without either. */
export function judgeHead(p: Pick<Provenance, 'judge' | 'judgements'> | null | undefined): string | null {
  const run = p?.judge
  // verification standard: one pass over what the word check doubted
  if (run?.mode === 'doubted' && (run.judged ?? 0) > 0) {
    return t('judge.headDoubted', { level: t(`judge.level.${run.level}`).toLowerCase(), model: run.model, judged: run.judged ?? 0, passed: passedOf(run.verdicts) }) + addedPart(run.verdicts)
  }
  if (run?.rounds && run.rounds.length > 0) {
    const first = run.rounds[0]
    const last = run.rounds[run.rounds.length - 1]
    return t('judge.headRun', {
      level: t(`judge.level.${run.level}`).toLowerCase(),
      // bulletproof: both judges' models
      model: run.second_model ? `${run.model} + ${run.second_model}` : run.model,
      passed: passedOf(last.verdicts),
      total: first.judged,
      rounds: tn('judge.rounds', run.rounds.length),
    }) + addedPart(last.verdicts)
  }
  const latest = p?.judgements?.[p.judgements.length - 1]
  if (latest) {
    const total = Object.values(latest.verdicts).reduce((a, b) => a + (b ?? 0), 0)
    return t('judge.headLater', { level: t(`judge.level.${latest.level}`).toLowerCase(), model: latest.model, passed: passedOf(latest.verdicts), total }) + addedPart(latest.verdicts)
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
  return (['supported', 'supported_elsewhere', 'contradicted', 'disputed', 'not_in_source', 'no_usable_answer'] as const)
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
  // not in source: the judge looked through every selected source
  const where = c.judge.verdict === 'not_in_source' ? `\n${t('judge.notInSourceTitle')}` : ''
  // bulletproof: both judges with their verdicts and reasons
  const second = c.judge.second
  const named = (v: JudgeVerdict | null) => t(`judge.verdict.${v ?? 'no_usable_answer'}`)
  const first = c.judge.first
  const both = second
    ? (first ? `\n${t('judge.first', { model: c.judge.model })}: ${named(first.verdict)} — ${first.reason}` : '') +
      `\n${t('judge.second', { model: second.model })}: ${named(second.verdict)} — ${second.reason}`
    : ''
  const title = (d ? `${c.judge.reason} — ${t('judge.disagreeTitle')}` : c.judge.reason) + where + both + word
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

/** The line under a chat answer the user's verification judged: "Judge
 *  (low, m): 2 of 3 doubted paragraphs supported" where only doubted
 *  paragraphs were judged (standard), "Judge (medium, m): 5 of 6 supported"
 *  where all were (thorough); from the paragraphs' own notes, null when
 *  none was judged. */
export function answerJudgeLine(units: readonly Claim[] | null | undefined): string | null {
  const judged = (units ?? []).filter((u) => u.judge)
  if (judged.length === 0) return null
  const { level, model } = judged[0].judge!
  const passed = judged.filter((u) => backed(u.judge!.verdict)).length
  const added = judged.filter((u) => u.judge!.verdict === 'supported_elsewhere').length
  const lvl = t(`judge.level.${level}`).toLowerCase()
  // standard judges only what the word check doubted, at low
  const all = (units ?? []).filter((u) => u.support).length
  const head = judged.length < all ? t('judge.headDoubted', { level: lvl, model, judged: judged.length, passed }) : t('judge.headLater', { level: lvl, model, passed, total: judged.length })
  return head + (added > 0 ? tn('judge.withAdded', added) : '')
}
