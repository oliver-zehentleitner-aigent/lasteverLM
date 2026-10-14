import { describe, expect, it } from 'vitest'
import type { DecisionContent } from '../api/types'
import { decisionOptions, decisionProblem, defaultDecision, modelVersusEvidence, orderedDistribution, percent, presetLevels, scalePercent } from './decision'

const keys = ['language', 'question', 'decision_type', 'choices', 'levels']

describe('the decision form', () => {
  const v = { ...defaultDecision(null), question: 'Should we migrate?' }

  it('starts as yes/no with two empty options and five preset levels', () => {
    expect(defaultDecision(null)).toMatchObject({ question: '', decisionType: 'yes_no', choices: ['', ''] })
    expect(presetLevels()).toEqual(['very unlikely', 'unlikely', 'uncertain', 'likely', 'very likely'])
  })

  it('needs a question within the limit', () => {
    expect(decisionProblem({ ...v, question: '  ' }, null)).toBe('Enter the question to decide.')
    expect(decisionProblem({ ...v, question: 'x'.repeat(501) }, null)).toContain('500')
    expect(decisionProblem(v, null)).toBeNull()
  })

  it('checks the list the type uses: count, empty entries, duplicates', () => {
    const choice = { ...v, decisionType: 'choice' as const }
    expect(decisionProblem({ ...choice, choices: ['A', ''] }, null)).toBe('Fill in or remove the empty entry.')
    expect(decisionProblem({ ...choice, choices: ['A'] }, null)).toBe('Give 2 to 8 options.')
    expect(decisionProblem({ ...choice, choices: ['A', 'a'] }, null)).toBe('Each entry only once.')
    expect(decisionProblem({ ...choice, choices: ['A', 'B'] }, null)).toBeNull()
    expect(decisionProblem({ ...v, decisionType: 'scale', levels: ['low', 'high'] }, null)).toBe('Give 3 to 7 levels.')
  })

  it('sends only the list the type uses, trimmed', () => {
    expect(decisionOptions({ ...v, choices: ['A', 'B'] }, keys)).toEqual({ question: 'Should we migrate?', decision_type: 'yes_no' })
    expect(decisionOptions({ ...v, decisionType: 'choice', choices: [' A ', 'B'] }, keys)).toEqual({ question: 'Should we migrate?', decision_type: 'choice', choices: ['A', 'B'] })
    expect(decisionOptions({ ...v, decisionType: 'scale' }, keys).levels).toHaveLength(5)
    expect(decisionOptions(v, ['language'])).toEqual({})
  })
})

describe('the decision view', () => {
  it('turns shares into whole percent, clamped', () => {
    expect(percent(0.724)).toBe(72)
    expect(percent(1.4)).toBe(100)
    expect(percent(Number.NaN)).toBe(0)
  })

  it('puts the scale marker on the segments\' middles', () => {
    expect(scalePercent(0, 5)).toBe(10)
    expect(scalePercent(2, 5)).toBe(50)
    expect(scalePercent(4, 5)).toBe(90)
    expect(scalePercent(2.4, 5)).toBeCloseTo(58)
    expect(scalePercent(9, 5)).toBe(90)
  })

  it('orders the distribution as the options were given', () => {
    expect(orderedDistribution({ B: 0.7, A: 0.2, X: 0.1 }, ['A', 'B', 'C'])).toEqual([
      { label: 'A', p: 0.2 },
      { label: 'B', p: 0.7 },
      { label: 'C', p: 0 },
      { label: 'X', p: 0.1 },
    ])
  })

  it('names a model answer the evidence does not share', () => {
    const c: DecisionContent = {
      question: 'q',
      decision_type: 'choice',
      verdict_text: '',
      evidence_for: [],
      evidence_against: [],
      gaps: [],
      agreement: 'conflicting',
      model_answer: { choice: 'B', distribution: { A: 0.3, B: 0.7 }, confidence: 0.6 },
      llm_choice: 'A',
    }
    expect(modelVersusEvidence(c)).toEqual({ model: 'B', evidence: 'A' })
    expect(modelVersusEvidence({ ...c, llm_choice: 'B' })).toBeNull()
    expect(modelVersusEvidence({ ...c, model_answer: { probability_yes: 0.6, answer: 'yes' } })).toBeNull()
  })
})
