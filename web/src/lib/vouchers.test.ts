import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { plausibleEmail, voucherError } from './vouchers'

describe('voucherError', () => {
  it('says what went wrong by the service code', () => {
    expect(voucherError(new ApiError(404, 'x', 'not_recoverable'))).toBe('Not recoverable: made before codes were kept.')
    expect(voucherError(new ApiError(429, 'x', 'too_many_mails'))).toContain('5 voucher mails')
    expect(voucherError(new ApiError(502, '550 mailbox unavailable', 'mail_failed'))).toContain('550 mailbox unavailable')
  })
  it("keeps the service's sentence otherwise", () => {
    expect(voucherError(new ApiError(404, 'unknown voucher'))).toBe('unknown voucher')
    expect(voucherError(new Error('network'))).toBe('network')
  })
})

describe('plausibleEmail', () => {
  it('takes a usual address and refuses obvious typos', () => {
    expect(plausibleEmail(' anna@example.org ')).toBe(true)
    expect(plausibleEmail('anna@example')).toBe(false)
    expect(plausibleEmail('anna example.org')).toBe(false)
  })
})
