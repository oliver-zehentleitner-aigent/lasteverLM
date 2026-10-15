import { describe, expect, it } from 'vitest'
import { shortId } from './outputId'

describe('shortId', () => {
  it('is the first 8 lowercase hex characters of the UUID', () => {
    expect(shortId('3F9C21AB-0d4e-4c1a-9b7e-1234567890ab')).toBe('3f9c21ab')
    expect(shortId('3f9c21ab0d4e4c1a9b7e1234567890ab')).toBe('3f9c21ab')
  })
})
