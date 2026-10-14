import { describe, expect, it } from 'vitest'
import type { AccountStats, IngestStats, RagStats, SystemInfo } from '../api/types'
import { attentionItems, kpiTiles, systemMeta } from './stats'

const account: AccountStats = {
  users: 3,
  logins_24h: 1,
  vouchers: { issued: 2, redeemed: 1, open: 1 },
  credits_granted_cents: 3000,
  usage_cost_cents: { total: 1310, last_24h: 120 },
  blocks_active: 0,
  bans_active: 2,
}
const ingest: IngestStats = { sources: { processing: 1, ready: 12, failed: 3 }, jobs: { pending: 0, running: 1, failed: 3 }, chunks: 640, source_bytes: 1 }
const rag: RagStats = {
  notebooks: { total: 4 },
  messages: { total: 38, last_24h: 5 },
  outputs: { by_kind: { report: 3, quiz: 2, table: 1, mindmap: 1, infographic: 0, audio: 1 }, by_status: { waiting: 0, processing: 1, ready: 6, failed: 1 } },
  jobs: { pending: 0, running: 1, failed: 1 },
  shared: { outputs: 2 },
}
const system: SystemInfo = {
  version: '0.7.1',
  commit: 'b44f38a9e',
  cluster: true,
  services: [
    { name: 'account', version: '0.7.1', commit: 'b44f38a', healthy: true },
    { name: 'ingest', version: 'unknown', commit: null, healthy: true },
    { name: 'rag', version: null, commit: null, healthy: false },
  ],
  pods: [],
  deployments: [],
}

describe('kpiTiles', () => {
  it('has six tiles, failures only as a detail', () => {
    const tiles = kpiTiles(account, ingest, rag)
    expect(tiles.map((x) => x.key)).toEqual(['users', 'logins', 'cost', 'vouchers', 'sources', 'documents'])
    expect(tiles.find((x) => x.key === 'sources')).toMatchObject({ value: '12', detail: '3 failed' })
    expect(tiles.find((x) => x.key === 'documents')).toMatchObject({ value: '8', detail: '1 failed' })
  })

  it('shows a dash for a service whose stats did not load', () => {
    const tiles = kpiTiles(null, ingest, null)
    expect(tiles.find((x) => x.key === 'users')?.value).toBe('—')
    expect(tiles.find((x) => x.key === 'documents')?.value).toBe('—')
    expect(tiles.find((x) => x.key === 'sources')?.value).toBe('12')
  })
})

describe('attentionItems', () => {
  it('lists only what has a page to act on', () => {
    expect(attentionItems(account, system).map((x) => [x.key, x.href])).toEqual([
      ['bans', '/admin/security'],
      ['down-rag', '/admin/system'],
      ['versions', '/admin/system'],
    ])
  })

  it('is empty when nothing needs action', () => {
    const fine = { ...system, services: system.services.map((s) => ({ ...s, healthy: true, version: '0.7.1' })) }
    expect(attentionItems({ ...account, bans_active: 0 }, fine)).toEqual([])
  })
})

describe('systemMeta', () => {
  it('reads as build and health', () => {
    expect(systemMeta(system)).toMatchObject({ build: 'v0.7.1 · b44f38a', health: '2 of 3 services healthy' })
    // the Git tag carries its own v: never "vv"
    expect(systemMeta({ ...system, version: 'v0.18.3' }).build).toBe('v0.18.3 · b44f38a')
    expect(systemMeta({ ...system, version: 'unknown', commit: 'unknown', services: [system.services[0]] })).toMatchObject({
      build: null,
      health: '1 service healthy',
    })
  })
})
