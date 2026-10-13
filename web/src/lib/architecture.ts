import type { SystemInfo } from '../api/types'
import { known, shortCommit } from './build'

/** The deployments the diagram draws, as the chart names them. */
export const DEPLOYMENTS = ['web', 'account', 'ingest', 'rag', 'ingest-worker', 'rag-worker'] as const
export type DeploymentName = (typeof DEPLOYMENTS)[number]

export interface NodeState {
  /** "2/2"; null when the cluster could not be read */
  replicas: string | null
  /** "0.8.2 · 81dff3d" from the service's healthz (workers run the API's image) */
  build: string | null
  /** false when not all replicas are ready or the service does not answer */
  healthy: boolean
}

/** The live numbers per box: replicas ready of total from the deployments,
 *  the build and health from the probed services. A worker shares its
 *  service's build; its health is its own replicas. */
export function architectureNodes(s: SystemInfo): Record<DeploymentName, NodeState> {
  const out = {} as Record<DeploymentName, NodeState>
  for (const name of DEPLOYMENTS) {
    const d = s.deployments.find((x) => x.name === name)
    const svcName = name.replace(/-worker$/, '')
    const svc = s.services.find((x) => x.name === svcName)
    const version = known(svc?.version)
    const commit = shortCommit(svc?.commit)
    const replicasOk = d ? d.ready >= d.replicas && d.replicas > 0 : true
    const serviceOk = name.endsWith('-worker') || name === 'web' ? true : (svc?.healthy ?? true)
    out[name] = {
      replicas: d ? `${d.ready}/${d.replicas}` : null,
      build: [version, commit].filter(Boolean).join(' · ') || null,
      healthy: replicasOk && serviceOk,
    }
  }
  return out
}
