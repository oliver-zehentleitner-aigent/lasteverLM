import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Output } from '../api/types'
import { STARTER_POLL_MAX_MS, STARTER_POLL_MS, awaitsStarterOutputs, pollStarterOutputs } from './starterOutputs'

const out = { id: 'o1' } as Output

describe('awaitsStarterOutputs', () => {
  it('waits while a notebook with starter sources has no outputs', () => {
    expect(awaitsStarterOutputs([{ starter: true }, {}], [])).toBe(true)
    // ingest's older name for the flag
    expect(awaitsStarterOutputs([{ demo: true }], [])).toBe(true)
  })
  it('does not wait with outputs, without starter sources, or before both lists are in', () => {
    expect(awaitsStarterOutputs([{ starter: true }], [out])).toBe(false)
    expect(awaitsStarterOutputs([{}, { starter: false }], [])).toBe(false)
    expect(awaitsStarterOutputs(null, [])).toBe(false)
    expect(awaitsStarterOutputs([{ starter: true }], null)).toBe(false)
  })
})

describe('pollStarterOutputs', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('lists every 2 s and stops at the first non-empty list', async () => {
    const list = vi.fn<() => Promise<Output[]>>().mockResolvedValueOnce([]).mockResolvedValueOnce([out])
    const onList = vi.fn()
    pollStarterOutputs(list, onList)
    await vi.advanceTimersByTimeAsync(STARTER_POLL_MS)
    expect(list).toHaveBeenCalledTimes(1)
    expect(onList).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(STARTER_POLL_MS)
    expect(onList).toHaveBeenCalledWith([out])
    await vi.advanceTimersByTimeAsync(STARTER_POLL_MS * 5)
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('gives up after 60 s', async () => {
    const list = vi.fn<() => Promise<Output[]>>().mockResolvedValue([])
    pollStarterOutputs(list, vi.fn())
    await vi.advanceTimersByTimeAsync(STARTER_POLL_MAX_MS)
    const calls = list.mock.calls.length
    // the last tick and the deadline fall on the same moment
    expect(calls).toBeGreaterThanOrEqual(STARTER_POLL_MAX_MS / STARTER_POLL_MS - 1)
    expect(calls).toBeLessThanOrEqual(STARTER_POLL_MAX_MS / STARTER_POLL_MS)
    await vi.advanceTimersByTimeAsync(STARTER_POLL_MS * 10)
    expect(list).toHaveBeenCalledTimes(calls)
  })

  it('retries after a failed list, and stops when cancelled', async () => {
    const list = vi.fn<() => Promise<Output[]>>().mockRejectedValueOnce(new Error('502')).mockResolvedValue([])
    const onList = vi.fn()
    const cancel = pollStarterOutputs(list, onList)
    await vi.advanceTimersByTimeAsync(STARTER_POLL_MS * 2)
    expect(list).toHaveBeenCalledTimes(2)
    cancel()
    await vi.advanceTimersByTimeAsync(STARTER_POLL_MS * 5)
    expect(list).toHaveBeenCalledTimes(2)
    expect(onList).not.toHaveBeenCalled()
  })

  it('drops a list that arrives after the cancel', async () => {
    let resolve: (o: Output[]) => void = () => {}
    const list = vi.fn(() => new Promise<Output[]>((r) => (resolve = r)))
    const onList = vi.fn()
    const cancel = pollStarterOutputs(list, onList)
    await vi.advanceTimersByTimeAsync(STARTER_POLL_MS)
    cancel()
    resolve([out])
    await vi.advanceTimersByTimeAsync(0)
    expect(onList).not.toHaveBeenCalled()
  })
})
