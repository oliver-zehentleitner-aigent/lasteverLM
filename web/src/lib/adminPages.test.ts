import { describe, expect, it } from 'vitest'
import { ADMIN_PAGES, adminPageFromPath, adminPath } from './adminPages'

describe('admin paths', () => {
  it('puts the overview at /admin and every other page under it', () => {
    expect(adminPath('overview')).toBe('/admin')
    expect(adminPath('system')).toBe('/admin/system')
  })

  it('reads every page back from its path', () => {
    for (const p of ADMIN_PAGES) expect(adminPageFromPath(adminPath(p.id))).toBe(p.id)
    expect(adminPageFromPath('/admin/overview')).toBe('overview')
    expect(adminPageFromPath('/admin/system/')).toBe('system')
  })

  it('is null for an unknown page or another route', () => {
    expect(adminPageFromPath('/admin/nope')).toBeNull()
    expect(adminPageFromPath('/admin/system/x')).toBeNull()
    expect(adminPageFromPath('/library')).toBeNull()
  })
})
