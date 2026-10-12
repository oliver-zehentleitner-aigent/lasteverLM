import { describe, expect, it } from 'vitest'
import { answerIndex, score } from './quiz'

const q = (answer: string | number) => ({ question: 'q', options: ['Alpha', 'Beta', 'Gamma'], answer, explanation: '' })

describe('answerIndex', () => {
  it('accepts an index, exact text and case-insensitive text', () => {
    expect(answerIndex(q(2))).toBe(2)
    expect(answerIndex(q('Beta'))).toBe(1)
    expect(answerIndex(q(' gamma '))).toBe(2)
  })
  it('returns -1 for an answer that matches nothing', () => {
    expect(answerIndex(q(7))).toBe(-1)
    expect(answerIndex(q('Delta'))).toBe(-1)
  })
})

describe('score', () => {
  it('counts answered and correct', () => {
    expect(score([q(0), q('Beta'), q(2)], [0, 0, null])).toEqual({ correct: 1, answered: 2 })
  })
})
