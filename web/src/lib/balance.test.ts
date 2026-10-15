import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { coalesced, onActivity, onBalanceRefresh, outputsFinished, readsFinished, requestBalanceRefresh, runningWork, startWork } from './balance'

describe('when the balance is reloaded', () => {
  it('after an output that was being made turns ready or failed', () => {
    expect(outputsFinished([{ id: 'a', status: 'processing' }], [{ id: 'a', status: 'ready' }])).toBe(true)
    expect(outputsFinished([{ id: 'a', status: 'waiting' }], [{ id: 'a', status: 'failed' }])).toBe(true)
    expect(outputsFinished([{ id: 'a', status: 'processing' }], [{ id: 'a', status: 'processing' }])).toBe(false)
    // one that was ready before, or a new one listed ready at once, changes nothing
    expect(outputsFinished([{ id: 'a', status: 'ready' }], [{ id: 'a', status: 'ready' }, { id: 'b', status: 'ready' }])).toBe(false)
  })

  it('after a source read ends', () => {
    expect(readsFinished([{ id: 's', status: 'processing' }], [{ id: 's', status: 'ready' }])).toBe(true)
    expect(readsFinished([{ id: 's', status: 'processing' }], [{ id: 's', status: 'failed' }])).toBe(true)
    expect(readsFinished([{ id: 's', status: 'added' }], [{ id: 's', status: 'added' }])).toBe(false)
  })

  it('when asked, through the one listener', () => {
    const seen = vi.fn()
    const off = onBalanceRefresh(seen)
    requestBalanceRefresh()
    off()
    requestBalanceRefresh()
    expect(seen).toHaveBeenCalledTimes(1)
  })

  it('counts running work and tells when it changes; every 30 s only while some runs', () => {
    const seen = vi.fn()
    const off = onActivity(seen)
    expect(runningWork()).toBe(0)
    const a = startWork()
    const b = startWork()
    expect(runningWork()).toBe(2)
    a()
    a()
    expect(runningWork()).toBe(1)
    b()
    expect(runningWork()).toBe(0)
    expect(seen).toHaveBeenCalledTimes(4)
    off()
  })
})

describe('coalesced', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })
  it('reloads once for a burst of asks, then again for the next', () => {
    const reload = vi.fn()
    const ask = coalesced(reload, 1000)
    ask()
    ask()
    ask()
    vi.advanceTimersByTime(1000)
    expect(reload).toHaveBeenCalledTimes(1)
    ask()
    vi.advanceTimersByTime(1000)
    expect(reload).toHaveBeenCalledTimes(2)
  })
})
