import type { Plan, PlanStep } from '../api/types'

/** A plan still moves: poll it. */
export const planActive = (p: Plan) => p.status === 'running'

/** What a done step links to, as a viewer tab; null for a step that made
 *  nothing to open (a listing, a library add, an explanation, which is a
 *  message in the chat). Pure, so it is tested. */
export function stepTarget(s: PlanStep): { type: 'source' | 'output'; id: string } | null {
  if (s.state !== 'done' && s.state !== 'waiting') return null
  if (s.tool === 'add_url' && s.result?.source_id) return { type: 'source', id: s.result.source_id }
  if (s.tool === 'create_output' && s.result?.output_id) return { type: 'output', id: s.result.output_id }
  return null
}

/** Whether a poll brought something the notebook's lists should show: a
 *  step that reached done (or waiting, for an output just created) since
 *  the last state, or the plan's end. */
export function planChangedWork(before: Plan, after: Plan): boolean {
  if (before.status !== after.status) return true
  return after.steps.some((s, i) => s.state !== before.steps[i]?.state && (s.state === 'done' || s.state === 'waiting'))
}
