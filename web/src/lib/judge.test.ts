import { describe, expect, it } from 'vitest'
import type { JudgeNote } from '../api/types'
import { disagrees, judgeBadge, judgeHead, verdictCounts } from './judge'

const note = (verdict: JudgeNote['verdict']): JudgeNote => ({ level: 'medium', model: 'glm-4.6', verdict, reason: 'the passage says 12', quote: '12 %', round: 1 })

describe('judge', () => {
  it('flags where the word check and the judge disagree', () => {
    expect(disagrees({ support: 'supported', judge: note('contradicted') })).toBe(true)
    expect(disagrees({ support: 'unsupported', judge: note('supported') })).toBe(true)
    expect(disagrees({ support: 'supported', judge: note('supported') })).toBe(false)
    expect(disagrees({ support: 'unverified', judge: note('contradicted') })).toBe(false)
    expect(disagrees({ support: 'supported' })).toBe(false)
  })

  it('heads a judged output with the passed claims and the rounds', () => {
    const judge = {
      level: 'medium' as const,
      model: 'glm-4.6',
      rounds: [
        { round: 1, judged: 9, verdicts: { supported: 6, contradicted: 3 }, usage: { tokens_in: 1, tokens_out: 1 } },
        { round: 2, judged: 3, verdicts: { supported: 7 }, usage: { tokens_in: 1, tokens_out: 1 } },
      ],
      removed: [],
    }
    expect(judgeHead({ judge })).toBe('Judge (medium, glm-4.6): 7 of 9 passed after 2 rounds')
    expect(judgeHead({ judgements: [{ level: 'low', model: 'm', verdicts: { supported: 5, not_in_source: 1 }, usage: { tokens_in: 1, tokens_out: 1 }, at: 'now' }] })).toBe('Judge (low, m): 5 of 6 supported')
    expect(judgeHead({})).toBeNull()
  })

  it('names the counts and the badge', () => {
    expect(verdictCounts({ supported: 5, contradicted: 1, not_in_source: 0 })).toBe('supported 5 · contradicted 1')
    expect(judgeBadge({ support: 'supported', judge: note('not_in_source') })).toMatchObject({ verdict: 'not_in_source', label: 'not in source', disagree: true })
    expect(judgeBadge({})).toBeNull()
  })

  it('shows a claim the judge gave no usable answer for as "no answer", never as a disagreement', () => {
    const none = { ...note(null), reason: 'the judge gave no usable answer: timeout' }
    expect(disagrees({ support: 'supported', judge: none })).toBe(false)
    expect(disagrees({ support: 'unsupported', judge: none })).toBe(false)
    expect(judgeBadge({ support: 'supported', judge: none })).toEqual({ verdict: 'no_usable_answer', label: 'no answer', title: 'the judge gave no usable answer: timeout', disagree: false })
    expect(verdictCounts({ supported: 4, no_usable_answer: 1 })).toBe('supported 4 · no answer 1')
  })
})
