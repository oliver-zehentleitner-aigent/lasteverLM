import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { confirmsEmail, deleteFailure } from './deleteUser'

describe('confirmsEmail', () => {
  it('takes the address as shown, case and spaces aside', () => {
    expect(confirmsEmail('new@example.org', 'new@example.org')).toBe(true)
    expect(confirmsEmail('  New@Example.org ', 'new@example.org')).toBe(true)
  })

  it('refuses anything else', () => {
    expect(confirmsEmail('new@example.or', 'new@example.org')).toBe(false)
    expect(confirmsEmail('', 'new@example.org')).toBe(false)
    expect(confirmsEmail('', '')).toBe(false)
  })
})

describe('deleteFailure', () => {
  it('names the step that failed on a 502', () => {
    const err = new ApiError(502, 'Bad gateway (502)', null, { step: 'ingest', message: 'timeout after 10 s' })
    const text = deleteFailure(err)
    expect(text).toContain('ingest')
    expect(text).toContain('timeout after 10 s')
  })

  it("falls back to the service's sentence", () => {
    expect(deleteFailure(new ApiError(409, 'you cannot delete your own account'))).toBe('you cannot delete your own account')
    expect(deleteFailure(new ApiError(502, 'Bad gateway (502)', null, null))).toBe('Bad gateway (502)')
    expect(deleteFailure(new ApiError(502, 'Bad gateway (502)', null, { message: 'x' }))).toBe('Bad gateway (502)')
  })
})
