import { describe, expect, it } from 'vitest'
import { canSeeAdmin, canWriteAdmin, roleOf } from './roles'

describe('roles', () => {
  it('reads the role, or derives it from is_admin for an older service', () => {
    expect(roleOf({ role: 'viewer', is_admin: false })).toBe('viewer')
    expect(roleOf({ is_admin: true })).toBe('admin')
    expect(roleOf({ is_admin: false })).toBe('user')
  })

  it('shows the panel to viewers and admins, writing to admins only', () => {
    expect([canSeeAdmin({ role: 'user', is_admin: false }), canSeeAdmin({ role: 'viewer', is_admin: false }), canSeeAdmin({ role: 'admin', is_admin: true })]).toEqual([false, true, true])
    expect([canWriteAdmin({ role: 'viewer', is_admin: false }), canWriteAdmin({ role: 'admin', is_admin: true })]).toEqual([false, true])
    expect(canSeeAdmin(null)).toBe(false)
    expect(canWriteAdmin(undefined)).toBe(false)
  })
})
