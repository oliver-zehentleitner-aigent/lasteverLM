import { describe, expect, it } from 'vitest'
import type { Plan, PlanStep } from '../api/types'
import { planChangedWork, stepTarget } from './plan'

const step = (over: Partial<PlanStep>): PlanStep => ({ n: 1, tool: 'add_url', args: {}, label: 'x', valid: true, estimate: { min: 0, max: 0 }, state: 'proposed', ...over })
const plan = (status: Plan['status'], steps: PlanStep[]): Plan => ({ plan_id: 'p', status, steps, estimate: { min: 0, max: 0 } })

describe('stepTarget', () => {
  it('opens a source or an output a step made', () => {
    expect(stepTarget(step({ state: 'done', result: { source_id: 's1' } }))).toEqual({ type: 'source', id: 's1' })
    expect(stepTarget(step({ tool: 'create_output', state: 'waiting', result: { output_id: 'o1' } }))).toEqual({ type: 'output', id: 'o1' })
  })

  it('has nothing to open before done, or for a listing', () => {
    expect(stepTarget(step({ state: 'running', result: { source_id: 's1' } }))).toBeNull()
    expect(stepTarget(step({ tool: 'list_sources', state: 'done', result: { sources: [] } }))).toBeNull()
  })
})

describe('planChangedWork', () => {
  it('is true when a step got done or the plan ended', () => {
    const a = plan('running', [step({ state: 'running' })])
    expect(planChangedWork(a, plan('running', [step({ state: 'done' })]))).toBe(true)
    expect(planChangedWork(a, plan('failed', [step({ state: 'running' })]))).toBe(true)
    expect(planChangedWork(a, plan('running', [step({ state: 'running' })]))).toBe(false)
  })
})
