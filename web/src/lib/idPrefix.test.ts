import { describe, expect, it } from 'vitest'
import { idPrefix } from './idPrefix'

describe('idPrefix', () => {
  it('takes a short ID, a full one with or without hyphens, any case', () => {
    expect(idPrefix('3f9c21ab')).toBe('3f9c21ab')
    expect(idPrefix(' 3F9C21AB-0d4e ')).toBe('3f9c21ab0d4e')
    expect(idPrefix('3f9c21ab-0d4e-4c1a-9b7e-1234567890ab')).toBe('3f9c21ab0d4e4c1a9b7e1234567890ab')
  })
  it('is null below 6 or above 32 hex characters, or with anything not hex', () => {
    expect(idPrefix('3f9c2')).toBeNull()
    expect(idPrefix('3f9c21ab0d4e4c1a9b7e1234567890ab0')).toBeNull()
    expect(idPrefix('3f9c21xz')).toBeNull()
    expect(idPrefix('')).toBeNull()
  })
})
