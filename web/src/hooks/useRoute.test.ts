import { describe, expect, it } from 'vitest'
import { parseRoute } from './useRoute'

describe('parseRoute', () => {
  it('maps the four app routes', () => {
    expect(parseRoute({ pathname: '/', search: '' })).toEqual({ name: 'home' })
    expect(parseRoute({ pathname: '/admin', search: '' })).toEqual({ name: 'admin', page: 'overview' })
    expect(parseRoute({ pathname: '/auth/callback', search: '?token=abc' })).toEqual({ name: 'auth-callback', token: 'abc' })
    expect(parseRoute({ pathname: '/s/t%20k', search: '' })).toEqual({ name: 'shared', token: 't k' })
    expect(parseRoute({ pathname: '/shared/notebook/abc', search: '' })).toEqual({ name: 'shared-notebook', token: 'abc' })
    expect(parseRoute({ pathname: '/shared/notebook/', search: '' })).toEqual({ name: 'home' })
    expect(parseRoute({ pathname: '/library', search: '' })).toEqual({ name: 'library' })
    expect(parseRoute({ pathname: '/settings', search: '' })).toEqual({ name: 'settings' })
  })
  it('falls back to home for unknown paths and keeps a missing token empty', () => {
    expect(parseRoute({ pathname: '/nope', search: '' })).toEqual({ name: 'home' })
    expect(parseRoute({ pathname: '/s/', search: '' })).toEqual({ name: 'home' })
    expect(parseRoute({ pathname: '/auth/callback', search: '' })).toEqual({ name: 'auth-callback', token: '' })
  })
  it('maps the admin pages, deep links included', () => {
    expect(parseRoute({ pathname: '/admin/users', search: '' })).toEqual({ name: 'admin', page: 'users' })
    expect(parseRoute({ pathname: '/admin/security/', search: '' })).toEqual({ name: 'admin', page: 'security' })
    expect(parseRoute({ pathname: '/admin/overview', search: '' })).toEqual({ name: 'admin', page: 'overview' })
    expect(parseRoute({ pathname: '/admin/nope', search: '' })).toEqual({ name: 'admin', page: 'overview' })
    expect(parseRoute({ pathname: '/administrator', search: '' })).toEqual({ name: 'home' })
  })
})
