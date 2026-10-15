import { useEffect } from 'react'
import type { Output, Source } from '../api/types'

/** The balance shown in the header and on the credits page is one value,
 *  the signed-in user's `balance_cents`, reloaded with the account (App
 *  holds it). This module says when: a paid action ended (an answer came,
 *  an output or a read finished, a plan or a judgement ended, a voucher
 *  was redeemed), every 30 s while paid work runs and never otherwise, and
 *  once when the tab is shown again. */
export const BALANCE_POLL_MS = 30_000
/** asks within this long of each other are one reload */
export const BALANCE_COALESCE_MS = 1_000

const events = new EventTarget()
const REFRESH = 'balance-refresh'
const ACTIVITY = 'balance-activity'
let running = 0

/** A paid action ended: reload the balance. */
export function requestBalanceRefresh(): void {
  events.dispatchEvent(new Event(REFRESH))
}

export function onBalanceRefresh(listener: () => void): () => void {
  events.addEventListener(REFRESH, listener)
  return () => events.removeEventListener(REFRESH, listener)
}

/** How many panes have paid work running now. */
export const runningWork = (): number => running

export function onActivity(listener: () => void): () => void {
  events.addEventListener(ACTIVITY, listener)
  return () => events.removeEventListener(ACTIVITY, listener)
}

/** Counts this pane's paid work as running while `on`: the balance is then
 *  reloaded every 30 s. */
export function useBalanceActivity(on: boolean): void {
  useEffect(() => (on ? startWork() : undefined), [on])
}

/** One piece of paid work starts; the returned function ends it (once). */
export function startWork(): () => void {
  running += 1
  events.dispatchEvent(new Event(ACTIVITY))
  let ended = false
  return () => {
    if (ended) return
    ended = true
    running -= 1
    events.dispatchEvent(new Event(ACTIVITY))
  }
}

const pending = (status: string) => status === 'waiting' || status === 'processing' || status === 'queued'

/** Whether an output that was being made is now ready or failed: what it
 *  cost is booked. */
export function outputsFinished(before: readonly Pick<Output, 'id' | 'status'>[], after: readonly Pick<Output, 'id' | 'status'>[]): boolean {
  const was = new Map(before.map((o) => [o.id, o.status]))
  return after.some((o) => pending(was.get(o.id) ?? '') && !pending(o.status))
}

/** Whether a source that was being read is now ready or failed. */
export function readsFinished(before: readonly Pick<Source, 'id' | 'status'>[], after: readonly Pick<Source, 'id' | 'status'>[]): boolean {
  const was = new Map(before.map((s) => [s.id, s.status as string]))
  return after.some((s) => pending(was.get(s.id) ?? '') && !pending(s.status))
}

/** Calls `reload` for a burst of asks once, after the first; a pure
 *  helper over the given timer so it is tested. */
export function coalesced(reload: () => void, wait = BALANCE_COALESCE_MS, timers: Pick<typeof globalThis, 'setTimeout' | 'clearTimeout'> = globalThis): () => void {
  let timer: ReturnType<typeof setTimeout> | null = null
  return () => {
    if (timer !== null) return
    timer = timers.setTimeout(() => {
      timer = null
      reload()
    }, wait)
  }
}
