import { judgeAskLabel, JUDGE_ASK_LEVEL } from '../lib/judge'
import { useEstimate } from './useEstimate'

/** "Have it judged · €0.02" for the claims the word check could not
 *  measure: priced at the level Check with a judge starts at (where the
 *  level can still be changed), asked for only when `needed`. `subject`
 *  is what the estimate needs of an output; none for a chat answer. */
export function useJudgeAskLabel(needed: boolean, subject?: { kind: string; question_count?: number; card_count?: number }): string {
  const price = useEstimate(needed ? { action: 'judge', options: { ...subject, level: JUDGE_ASK_LEVEL } } : null, 0)
  return judgeAskLabel(price)
}
