import { describe, expect, it } from 'vitest'
import type { SystemInfo } from '../api/types'
import { architectureNodes } from './architecture'

const system: SystemInfo = {
  version: '0.8.2',
  commit: '81dff3d9',
  cluster: true,
  services: [
    { name: 'account', version: '0.8.2', commit: '81dff3d9', healthy: true },
    { name: 'ingest', version: '0.8.2', commit: '81dff3d9', healthy: true },
    { name: 'rag', version: 'unknown', commit: null, healthy: false },
  ],
  pods: [],
  deployments: [
    { name: 'web', replicas: 2, ready: 2, updated: 2 },
    { name: 'account', replicas: 1, ready: 1, updated: 1 },
    { name: 'ingest-worker', replicas: 2, ready: 1, updated: 2 },
    { name: 'rag', replicas: 1, ready: 1, updated: 1 },
  ],
}

describe('architectureNodes', () => {
  const n = architectureNodes(system)

  it('fills replicas and the build per box', () => {
    expect(n.account).toEqual({ replicas: '1/1', build: '0.8.2 · 81dff3d', healthy: true })
    expect(n['ingest-worker'].build).toBe('0.8.2 · 81dff3d')
  })

  it('marks a box unhealthy for missing replicas or a service that does not answer', () => {
    expect(n['ingest-worker'].healthy).toBe(false)
    expect(n.rag).toMatchObject({ replicas: '1/1', build: null, healthy: false })
  })

  it('has no numbers for a deployment the cluster did not list', () => {
    expect(n.ingest).toMatchObject({ replicas: null, healthy: true })
  })
})
