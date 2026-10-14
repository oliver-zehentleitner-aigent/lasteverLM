import { describe, expect, it } from 'vitest'
import { ADMIN_PAGES, FINANCE_PAGES, adminPageFromPath, adminPath, financePageFromPath, financePath } from './adminPages'

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

describe('finance paths', () => {
  it('reads every finance page back, costs at /admin/finance', () => {
    for (const p of FINANCE_PAGES) {
      expect(adminPageFromPath(financePath(p.id))).toBe('finance')
      expect(financePageFromPath(financePath(p.id))).toBe(p.id)
    }
    expect(financePath('costs')).toBe('/admin/finance')
  })

  it('sends the old credits page to the vouchers', () => {
    expect(adminPageFromPath('/admin/credits')).toBe('finance')
    expect(financePageFromPath('/admin/credits')).toBe('vouchers')
  })

  it('is null for an unknown finance page', () => {
    expect(adminPageFromPath('/admin/finance/nope')).toBeNull()
    expect(financePageFromPath('/admin/security')).toBeNull()
  })
})
