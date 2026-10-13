import { describe, expect, it } from 'vitest'
import type { AccountStats, IngestStats, RagStats } from '../api/types'
import { formatBytes } from './format'
import { accountTiles, ingestTiles, ragTiles, type StatTile } from './stats'

const ingest: IngestStats = {
  sources: { processing: 3, ready: 120, failed: 4 },
  jobs: { pending: 1, running: 2, failed: 4 },
  chunks: 581,
  source_bytes: 73400320,
}

const rag: RagStats = {
  notebooks: { total: 5 },
  messages: { total: 40, last_24h: 6 },
  outputs: {
    by_kind: { report: 3, quiz: 1, table: 0, mindmap: 0, infographic: 0, audio: 2 },
    by_status: { waiting: 0, processing: 1, ready: 4, failed: 1 },
  },
  jobs: { pending: 0, running: 1, failed: 1 },
  shared: { outputs: 2 },
}

const byLabel = (tiles: StatTile[], label: string) => tiles.find((t) => t.label === label)

describe('stats tiles', () => {
  it('flags failed sources and shows the storage size', () => {
    const tiles = ingestTiles(ingest)
    expect(byLabel(tiles, 'Sources failed')).toMatchObject({ value: '4', alert: true })
    expect(byLabel(tiles, 'Stored sources')?.value).toBe('70.0 MB')
  })

  it('sums documents over their status and lists only the kinds present', () => {
    const tiles = ragTiles(rag)
    expect(byLabel(tiles, 'Documents')).toMatchObject({ value: '6', detail: 'Report 3 · Quiz 1 · Audio 2' })
  })

  it('does not flag zero failures', () => {
    const tiles = ragTiles({ ...rag, outputs: { ...rag.outputs, by_status: { ...rag.outputs.by_status, failed: 0 } } })
    expect(byLabel(tiles, 'Documents failed')?.alert).toBe(false)
  })
})

describe('formatBytes', () => {
  it('keeps bytes whole and scales the rest', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
  })
})

describe('account tiles', () => {
  const account: AccountStats = {
    users: 3,
    logins_24h: 1,
    vouchers: { issued: 2, redeemed: 1, open: 1 },
    credits_granted_cents: 3000,
    usage_cost_cents: { total: 1310, last_24h: 120 },
    blocks_active: 0,
    bans_active: 0,
  }

  it('link credit and vouchers to the pages that explain them', () => {
    const tiles = accountTiles(account)
    expect(byLabel(tiles, 'Credit granted')?.href).toBe('/admin/users')
    expect(byLabel(tiles, 'Vouchers open')?.href).toBe('/admin/credits')
    expect(byLabel(tiles, 'Users')?.href).toBeUndefined()
  })
})
