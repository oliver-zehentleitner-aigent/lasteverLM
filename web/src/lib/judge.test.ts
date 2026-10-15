import { describe, expect, it } from 'vitest'
import type { JudgeNote } from '../api/types'
import { answerJudgeLine, disagrees, judgeAskLabel, judgeBadge, judgeHead, verdictCounts } from './judge'

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

describe('the word check under a verdict', () => {
  it("moves into the judge badge's tooltip", () => {
    expect(judgeBadge({ support: 'unverified', judge: note('supported') })?.title).toBe('the passage says 12\nNot word-checked (other language)')
    // no verdict: the word check keeps its own badge, the tooltip stays the reason
    expect(judgeBadge({ support: 'unverified', judge: { ...note(null), reason: 'no usable answer' } })?.title).toBe('no usable answer')
  })
})

describe('judgeAskLabel', () => {
  it('names the price once it is known', () => {
    expect(judgeAskLabel({ estimate: { charge_cents_min: 2, charge_cents_max: 2 } } as never)).toMatch(/^Have it judged · .*0\.02/)
    expect(judgeAskLabel(null)).toBe('Have it judged')
    expect(judgeAskLabel({ failed: 'x' })).toBe('Have it judged')
  })
})

describe('a judge on what the word check doubted (verification standard)', () => {
  it('heads with the doubted paragraphs, none when nothing was doubted', () => {
    const run = { mode: 'doubted' as const, judged: 3, level: 'low' as const, model: 'm', verdicts: { supported: 2, contradicted: 1 } }
    expect(judgeHead({ judge: run })).toBe('Judge (low, m): 2 of 3 doubted paragraphs supported')
    expect(judgeHead({ judge: { ...run, judged: 0, verdicts: {} } })).toBeNull()
  })
})

describe('answerJudgeLine', () => {
  const j = (verdict: 'supported' | 'contradicted', level: 'low' | 'medium' = 'low') => ({ level, model: 'm', verdict, reason: '', quote: '', round: 1 })
  it('names a judging of the doubted paragraphs, or of all of them', () => {
    expect(answerJudgeLine([{ support: 'supported' }, { support: 'unsupported', judge: j('supported') }, { support: 'unverified', judge: j('contradicted') }])).toBe('Judge (low, m): 1 of 2 doubted paragraphs supported')
    expect(answerJudgeLine([{ support: 'supported', judge: j('supported', 'medium') }, { support: 'unsupported', judge: j('contradicted', 'medium') }])).toBe('Judge (medium, m): 1 of 2 supported')
  })
  it('is null without a judged paragraph', () => {
    expect(answerJudgeLine([{ support: 'supported' }])).toBeNull()
    expect(answerJudgeLine(null)).toBeNull()
  })
})
