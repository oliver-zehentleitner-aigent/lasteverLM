import type { Output } from '../api/types'

/** rag copies a starter notebook's outputs from a queue, a moment after
 *  ingest copied the notebook; the web opens the copy at once, so its
 *  first outputs list can come back empty. Neither service says a copy is
 *  still pending, so the open notebook asks again while it has starter
 *  sources and no outputs. */
export const STARTER_POLL_MS = 2000
export const STARTER_POLL_MAX_MS = 60_000

/** Whether the outputs of a starter copy may still be on their way. */
export function awaitsStarterOutputs(sources: readonly { starter?: boolean; demo?: boolean }[] | null, outputs: readonly Output[] | null): boolean {
  if (!sources || !outputs) return false
  return outputs.length === 0 && sources.some((s) => s.starter || s.demo)
}

/** Lists the outputs every `STARTER_POLL_MS` until one arrives or
 *  `STARTER_POLL_MAX_MS` passed; a failed list is retried on the next tick.
 *  Returns the cancel. */
export function pollStarterOutputs(list: () => Promise<Output[]>, onList: (outputs: Output[]) => void): () => void {
  let stopped = false
  const stop = () => {
    stopped = true
    clearInterval(timer)
    clearTimeout(deadline)
  }
  const timer = setInterval(() => {
    list().then(
      (outputs) => {
        if (stopped) return
        if (outputs.length > 0) {
          stop()
          onList(outputs)
        }
      },
      () => {
        // retried on the next tick
      },
    )
  }, STARTER_POLL_MS)
  const deadline = setTimeout(stop, STARTER_POLL_MAX_MS)
  return stop
}
