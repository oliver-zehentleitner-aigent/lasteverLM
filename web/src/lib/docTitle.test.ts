import { describe, expect, it } from 'vitest'
import { TITLE_PART_MAX, docTitle, routeTitle } from './docTitle'

describe('docTitle', () => {
  it('names the document, the notebook and the app, most specific first', () => {
    expect(docTitle('Report', 'My notebook')).toBe('Report · My notebook · lasteverLM')
    expect(docTitle('Admin', 'Finance', 'Costs')).toBe('Admin · Finance · Costs · lasteverLM')
    expect(docTitle()).toBe('lasteverLM')
  })
  it('leaves out empty parts and cuts long ones', () => {
    expect(docTitle(null, '  My   notebook ', undefined)).toBe('My notebook · lasteverLM')
    const long = 'x'.repeat(100)
    const part = docTitle(long).split(' · ')[0]
    expect(part.length).toBe(TITLE_PART_MAX)
    expect(part.endsWith('…')).toBe(true)
  })
  it('keeps markup as plain text', () => {
    expect(docTitle('<b>bold</b>')).toBe('<b>bold</b> · lasteverLM')
  })
})

describe('routeTitle', () => {
  it('names the app pages', () => {
    expect(routeTitle({ name: 'library' }, '/library', true)).toBe('Library · lasteverLM')
    expect(routeTitle({ name: 'settings' }, '/settings', true)).toBe('Settings · lasteverLM')
    expect(routeTitle({ name: 'prices' }, '/prices', false)).toBe('Prices · lasteverLM')
    expect(routeTitle({ name: 'admin', page: 'finance' }, '/admin/finance/costs', true)).toBe('Admin · Finance · Costs · lasteverLM')
    expect(routeTitle({ name: 'admin', page: 'finance' }, '/admin/finance', true)).toBe('Admin · Finance · Revenue and profit · lasteverLM')
  })
  it('leaves the workspace and the shared pages to themselves, and is the bare name signed out', () => {
    expect(routeTitle({ name: 'home' }, '/', true)).toBeNull()
    expect(routeTitle({ name: 'shared', token: 'x' }, '/s/x', false)).toBeNull()
    expect(routeTitle({ name: 'home' }, '/', false)).toBe('lasteverLM')
  })
})
