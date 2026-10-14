import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { rag } from '../api/rag'
import { estimateKey, type Estimate, type EstimateRequest } from '../lib/estimate'

/** An estimate, or why there is none to show: `noRate` while pricing has
 *  no exchange rate (the action itself would fail the same way), `failed`
 *  with the error for any other failure, so a missing price never reads
 *  as a free action. */
export type EstimateState = { estimate: Estimate } | { noRate: true } | { failed: string } | null

// one request per distinct question for a few minutes: the chat's price is
// asked by every conversation, and prices change rarely
const TTL_MS = 5 * 60 * 1000
const cache = new Map<string, { at: number; result: Promise<EstimateState> }>()

function load(req: EstimateRequest): Promise<EstimateState> {
  const key = estimateKey(req)
  const hit = cache.get(key)
  if (hit && Date.now() - hit.at < TTL_MS) return hit.result
  const result = rag.estimate(req).then(
    (estimate): EstimateState => ({ estimate }),
    (e: unknown): EstimateState => {
      // a failure is asked again next time (options that do not fit yet, rag restarting)
      cache.delete(key)
      if (e instanceof ApiError && e.status === 503) return { noRate: true }
      return { failed: e instanceof Error ? e.message : String(e) }
    },
  )
  cache.set(key, { at: Date.now(), result })
  return result
}

/** The estimate of `req`, asked `delayMs` after it stops changing (the
 *  options are typed into); null while there is none, and while a changed
 *  request is not answered yet. A null `req` asks nothing. */
export function useEstimate(req: EstimateRequest | null, delayMs = 400): EstimateState {
  const [answered, setAnswered] = useState<{ key: string; state: EstimateState } | null>(null)
  // the key stands for the request, which is a new object on every render
  const key = req ? estimateKey(req) : null
  useEffect(() => {
    if (key === null) return
    let live = true
    const timer = setTimeout(() => void load(JSON.parse(key) as EstimateRequest).then((state) => live && setAnswered({ key, state })), delayMs)
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [key, delayMs])
  return answered && answered.key === key ? answered.state : null
}
