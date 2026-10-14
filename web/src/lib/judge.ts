import type { Claim, JudgeVerdict, Provenance } from '../api/types'
import { t, tn } from '../i18n'

/** The judge's verdicts as the views show them. Pure, so it is tested. */

/** Where the word check and the judge read a claim differently: the check
 *  backed it and the judge did not, or the other way round. A claim the
 *  check could not measure (another language) is no disagreement. */
export function disagrees(c: Claim): boolean {
  if (!c.judge || !c.support || c.support === 'unverified') return false
  return (c.support === 'supported') !== (c.judge.verdict === 'supported')
}

/** "Judge (medium, glm-4.6): 7 of 9 passed after 2 rounds" for a judging
 *  while it was made; "Judge (low, …): 5 of 6 supported" for the latest
 *  one asked for afterwards; null without either. */
export function judgeHead(p: Pick<Provenance, 'judge' | 'judgements'> | null | undefined): string | null {
  const run = p?.judge
  if (run && run.rounds.length > 0) {
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

/** The counts of a round or a judging, as "supported 5 · contradicted 1". */
export function verdictCounts(v: Partial<Record<JudgeVerdict, number>>): string {
  return (['supported', 'contradicted', 'not_in_source'] as const)
    .filter((k) => (v[k] ?? 0) > 0)
    .map((k) => `${t(`judge.verdict.${k}`)} ${v[k]}`)
    .join(' · ')
}

/** The badge's text and its tooltip (the judge's reason). */
export function judgeBadge(c: Claim): { verdict: JudgeVerdict; label: string; title: string; disagree: boolean } | null {
  if (!c.judge) return null
  const d = disagrees(c)
  const title = d ? `${c.judge.reason} — ${t('judge.disagreeTitle')}` : c.judge.reason
  return { verdict: c.judge.verdict, label: t(`judge.verdict.${c.judge.verdict}`), title, disagree: d }
}
