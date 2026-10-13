import { describe, expect, it } from 'vitest'
import { afterSources, wizardSteps } from './wizard'

describe('afterSources', () => {
  it('goes on to the outputs for a new notebook', () => {
    expect(afterSources(true, 0)).toBe('outputs')
    expect(afterSources(true, 2)).toBe('outputs')
  })

  it('ends after the sources when adding, with a note when some were there', () => {
    expect(afterSources(false, 0)).toBe('done')
    expect(afterSources(false, 1)).toBe('note')
  })
})

describe('wizardSteps', () => {
  it('counts the output step only for a new notebook', () => {
    expect(wizardSteps(true)).toBe(3)
    expect(wizardSteps(false)).toBe(2)
  })
})
