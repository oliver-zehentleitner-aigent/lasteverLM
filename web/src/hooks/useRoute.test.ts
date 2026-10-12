import { describe, expect, it } from 'vitest'
import { parseRoute } from './useRoute'

describe('parseRoute', () => {
  it('maps the four app routes', () => {
    expect(parseRoute({ pathname: '/', search: '' })).toEqual({ name: 'home' })
    expect(parseRoute({ pathname: '/admin', search: '' })).toEqual({ name: 'admin' })
    expect(parseRoute({ pathname: '/auth/callback', search: '?token=abc' })).toEqual({ name: 'auth-callback', token: 'abc' })
    expect(parseRoute({ pathname: '/s/t%20k', search: '' })).toEqual({ name: 'shared', token: 't k' })
  })
  it('falls back to home for unknown paths and keeps a missing token empty', () => {
    expect(parseRoute({ pathname: '/nope', search: '' })).toEqual({ name: 'home' })
    expect(parseRoute({ pathname: '/s/', search: '' })).toEqual({ name: 'home' })
    expect(parseRoute({ pathname: '/auth/callback', search: '' })).toEqual({ name: 'auth-callback', token: '' })
  })
})
