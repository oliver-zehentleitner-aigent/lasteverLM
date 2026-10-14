import { describe, expect, it } from 'vitest'
import { NO_RATE_REASON, pendingReason } from './pendingReason'

describe('pendingReason', () => {
  it('shows the missing rate as it comes, while processing and while waiting', () => {
    expect(pendingReason('processing', NO_RATE_REASON)).toEqual({ text: NO_RATE_REASON, admin: true })
    expect(pendingReason('waiting_for_credit', NO_RATE_REASON)).toEqual({ text: NO_RATE_REASON, admin: true })
  })

  it('calls another error while processing a retry', () => {
    expect(pendingReason('processing', 'timeout')).toEqual({ text: 'Retrying after: timeout', admin: false })
  })

  it('shows another error while waiting for credit as it comes', () => {
    expect(pendingReason('waiting_for_credit', 'something')).toEqual({ text: 'something', admin: false })
  })

  it('says nothing without an error, or for a finished or failed source', () => {
    expect(pendingReason('processing', null)).toBeNull()
    expect(pendingReason('ready', 'x')).toBeNull()
    expect(pendingReason('failed', 'x')).toBeNull()
  })
})
