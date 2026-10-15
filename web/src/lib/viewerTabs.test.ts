import { describe, expect, it } from 'vitest'
import { afterClose, chunkPageOffset, tabUrl, heldUrl, URL_FRESH_MS, defaultView, dropMissing, openTab, readTabs, tabKey, writeTabs, type ViewerTab, tabsToClose } from './viewerTabs'

const memory = () => {
  const m = new Map<string, string>()
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) }
}

describe('viewerTabs', () => {
  it('appends in the order of opening and refocuses an open one with its new target', () => {
    let tabs: ViewerTab[] = []
    tabs = openTab(tabs, { type: 'output', id: 'o1' })
    tabs = openTab(tabs, { type: 'source', id: 's1', page: 3 })
    tabs = openTab(tabs, { type: 'output', id: 'o2' })
    expect(tabs.map(tabKey)).toEqual(['output:o1', 'source:s1', 'output:o2'])
    tabs = openTab(tabs, { type: 'source', id: 's1', page: 5, chunkId: 'c7' })
    expect(tabs.map(tabKey)).toEqual(['output:o1', 'source:s1', 'output:o2'])
    expect(tabs[1]).toEqual({ type: 'source', id: 's1', page: 5, chunkId: 'c7', nonce: 2 })
  })

  it('moves to the right neighbour on close, else the left', () => {
    expect(afterClose(['a', 'b', 'c'], 'b')).toBe('c')
    expect(afterClose(['a', 'b', 'c'], 'c')).toBe('b')
    expect(afterClose(['a'], 'a')).toBeNull()
  })

  it('opens text and web pages as read, the rest as the original', () => {
    expect(defaultView('text')).toBe('read')
    expect(defaultView('url')).toBe('read')
    expect(defaultView('pdf')).toBe('original')
    expect(defaultView('image')).toBe('original')
  })

  it('keeps the tabs and the active one per notebook, without targets', () => {
    const s = memory()
    writeTabs(s, 'nb', { tabs: [{ type: 'source', id: 's1', page: 4, nonce: 3 }, { type: 'output', id: 'o1' }], active: 'output:o1' })
    expect(readTabs(s, 'nb')).toEqual({ tabs: [{ type: 'source', id: 's1' }, { type: 'output', id: 'o1' }], active: 'output:o1' })
    expect(readTabs(s, 'other')).toEqual({ tabs: [], active: null })
    writeTabs(s, 'nb', { tabs: [], active: null })
    expect(readTabs(s, 'nb').tabs).toEqual([])
  })

  it('ignores what it cannot read', () => {
    const s = memory()
    s.setItem('lasteverlm.tabs.nb', '{"tabs":[{"type":"x","id":"1"},{"type":"output","id":"o"}],"active":"output:gone"}')
    expect(readTabs(s, 'nb')).toEqual({ tabs: [{ type: 'output', id: 'o' }], active: null })
    s.setItem('lasteverlm.tabs.nb', 'not json')
    expect(readTabs(s, 'nb')).toEqual({ tabs: [], active: null })
  })

  it('drops the tabs of one type that are gone, and keeps the array when none is', () => {
    const tabs: ViewerTab[] = [{ type: 'output', id: 'o1' }, { type: 'source', id: 's1' }, { type: 'output', id: 'o2' }]
    expect(dropMissing(tabs, 'output', new Set(['o1'])).map(tabKey)).toEqual(['output:o1', 'source:s1'])
    expect(dropMissing(tabs, 'source', new Set(['s1']))).toBe(tabs)
  })
})

describe('chunkPageOffset', () => {
  it('opens the page of chunks the cited one is on', () => {
    expect(chunkPageOffset(null)).toBe(0)
    expect(chunkPageOffset(49)).toBe(0)
    expect(chunkPageOffset(50)).toBe(50)
    expect(chunkPageOffset(137)).toBe(100)
  })
})

describe('heldUrl', () => {
  const tab: ViewerTab = { type: 'source', id: 's1', url: 'https://s/a?sig=1', urlAt: 0 }

  it('keeps the address a tab opened with while the list hands out new ones', () => {
    expect(heldUrl(tab, 'https://s/a?sig=2', 60_000)).toBe(tab)
  })

  it('takes the list\'s when it had none or its own is about to expire', () => {
    expect(heldUrl({ type: 'source', id: 's1' }, 'https://s/a?sig=2', 5)).toEqual({ type: 'source', id: 's1', url: 'https://s/a?sig=2', urlAt: 5 })
    expect(heldUrl(tab, 'https://s/a?sig=3', URL_FRESH_MS + 1).url).toBe('https://s/a?sig=3')
  })

  it('leaves output tabs alone', () => {
    const out: ViewerTab = { type: 'output', id: 'o1' }
    expect(heldUrl(out, 'x', 1)).toBe(out)
  })
})

describe('tabUrl', () => {
  it('holds a web page\'s snapshot and any other source\'s file', () => {
    expect(tabUrl({ kind: 'url', preview_url: 'https://example.org/page', snapshot_url: 'https://s/snap?sig=1' })).toBe('https://s/snap?sig=1')
    expect(tabUrl({ kind: 'url', preview_url: 'https://example.org/page', snapshot_url: null })).toBeNull()
    expect(tabUrl({ kind: 'pdf', preview_url: 'https://s/a.pdf?sig=1' })).toBe('https://s/a.pdf?sig=1')
  })
})

describe('closing several tabs', () => {
  const keys = ['a', 'b', 'c', 'd']
  it('picks all, the others, or those to the right', () => {
    expect(tabsToClose(keys, 'b', 'all')).toEqual(keys)
    expect(tabsToClose(keys, 'b', 'others')).toEqual(['a', 'c', 'd'])
    expect(tabsToClose(keys, 'b', 'right')).toEqual(['c', 'd'])
    expect(tabsToClose(keys, 'd', 'right')).toEqual([])
    expect(tabsToClose(keys, 'x', 'others')).toEqual([])
  })
})
