import { describe, expect, it } from 'vitest'
import type { SystemInfo } from '../api/types'
import { architectureNodes, dependencyState } from './architecture'

const pod = (service: string, tag: string, restarts = 0, reason: string | null = null) => ({ name: `${service}-x`, service, image_tag: tag, ready: true, restarts, node: 'n1', started_at: null, reason })

const system: SystemInfo = {
  version: '0.8.2',
  commit: '81dff3d9',
  cluster: true,
  services: [
    { name: 'account', version: '0.8.2', commit: '81dff3d9', healthy: true },
    { name: 'ingest', version: '0.8.2', commit: '81dff3d9', healthy: true },
    { name: 'rag', version: 'unknown', commit: null, healthy: false },
  ],
  pods: [pod('web', '0.8.2'), pod('web', '0.8.1'), pod('account', '0.8.2'), pod('ingest-worker', '0.8.2', 2)],
  deployments: [
    { name: 'web', replicas: 2, ready: 2, updated: 2 },
    { name: 'account', replicas: 1, ready: 1, updated: 1 },
    { name: 'ingest-worker', replicas: 2, ready: 1, updated: 2 },
    { name: 'rag', replicas: 1, ready: 1, updated: 1 },
    { name: 'rag-worker', replicas: 1, ready: 0, updated: 1 },
  ],
}

describe('architectureNodes', () => {
  const n = architectureNodes(system)

  it('fills replicas and the build per box', () => {
    expect(n.account).toEqual({ replicas: '1/1', build: '0.8.2 · 81dff3d', state: 'ok', restarts: 0, reasons: [] })
    expect(n['ingest-worker'].build).toBe('0.8.2 · 81dff3d')
  })

  it('is amber when partly ready or restarted, and while rolling out', () => {
    expect(n['ingest-worker']).toMatchObject({ state: 'warn', restarts: 2, reasons: ['partly', 'restarts'] })
    // two image tags under one deployment: a rollout in progress
    expect(n.web).toMatchObject({ state: 'warn', reasons: ['rolling'] })
  })

  it('never calls a rollout a failure, even with nothing ready yet', () => {
    const s = { ...system, deployments: [{ name: 'rag-worker', replicas: 1, ready: 0, updated: 1, progressing: true }] }
    expect(architectureNodes(s)['rag-worker']).toMatchObject({ state: 'warn', reasons: ['rolling'] })
  })

  it('is red for failure: nothing ready outside a rollout, no answer, a failing pod, climbing restarts', () => {
    expect(n['rag-worker']).toMatchObject({ state: 'down', reasons: ['notReady'] })
    expect(n.rag).toMatchObject({ replicas: '1/1', build: null, state: 'down', reasons: ['noAnswer'] })
    const crashing = { ...system, pods: [pod('account', '0.8.2', 4, 'CrashLoopBackOff')] }
    expect(architectureNodes(crashing).account).toMatchObject({ state: 'down', reasons: ['crash', 'restarts'] })
    const later = { ...system, pods: system.pods.map((p) => (p.service === 'ingest-worker' ? { ...p, restarts: 3 } : p)) }
    expect(architectureNodes(later, system)['ingest-worker']).toMatchObject({ state: 'down', reasons: ['climbing', 'partly'] })
  })

  it('goes by healthz alone without the cluster, and is unknown where there is none', () => {
    const local = architectureNodes({ ...system, cluster: false, pods: [], deployments: [] })
    expect(local.ingest).toMatchObject({ replicas: null, state: 'ok' })
    expect(local.rag.state).toBe('down')
    expect(local.web.state).toBe('unknown')
    expect(local['rag-worker'].state).toBe('unknown')
  })
})

describe('dependencyState', () => {
  it('is grey until a service reports it, red when one says down', () => {
    expect(dependencyState(system, 'postgres')).toBe('unknown')
    const reported = {
      ...system,
      services: [
        { ...system.services[0], dependencies: { postgres: 'ok' as const } },
        { ...system.services[1], dependencies: { postgres: 'ok' as const, storage: 'down' as const } },
      ],
    }
    expect(dependencyState(reported, 'postgres')).toBe('ok')
    expect(dependencyState(reported, 'storage')).toBe('down')
    expect(dependencyState(reported, 'inference')).toBe('unknown')
  })
})
