import type { Dependency, SystemInfo } from '../api/types'
import { known, shortCommit } from './build'

/** The deployments the diagram draws, as the chart names them. */
export const DEPLOYMENTS = ['web', 'account', 'ingest', 'rag', 'ingest-worker', 'rag-worker'] as const
export type DeploymentName = (typeof DEPLOYMENTS)[number]

/** The colour a box takes. A rollout is never a failure: amber while one
 *  is under way or replicas are only partly ready (4 of 5) or pods have
 *  restarted; red only for failure (a pod crash-looping, erroring or
 *  killed for memory, restarts still climbing, nothing ready outside a
 *  rollout, healthz not answering); grey when nothing is known. */
export type NodeHealth = 'ok' | 'warn' | 'down' | 'unknown'

export type Reason = 'crash' | 'climbing' | 'notReady' | 'noAnswer' | 'rolling' | 'partly' | 'restarts'

export interface NodeState {
  /** "2/2"; null when the cluster could not be read */
  replicas: string | null
  /** "0.8.2 · 81dff3d" from the service's healthz (workers run the API's image) */
  build: string | null
  state: NodeHealth
  /** restarts of the current pods */
  restarts: number
  /** why it is not ok, for the box's tooltip; empty when it is */
  reasons: Reason[]
}

const FAILED = /^(CrashLoopBackOff|Error|OOMKilled|ImagePullBackOff|ErrImagePull|CreateContainerError)$/
const DOWN: ReadonlySet<Reason> = new Set(['crash', 'climbing', 'notReady', 'noAnswer'])

/** The live numbers and colour per box. Replicas and the rollout from the
 *  deployment (its Progressing condition when reported, else fewer
 *  replicas updated than wanted, or two image tags among its pods), the
 *  failure reasons and restarts from its pods (labelled with the
 *  deployment's name), build and health from the probed service.
 *  `previous` is the last refresh: restarts that grew since are climbing.
 *  A worker shares its service's build; its health is its own replicas.
 *  Without cluster data an API service is as its healthz says, web and the
 *  workers are unknown. */
export function architectureNodes(s: SystemInfo, previous: SystemInfo | null = null): Record<DeploymentName, NodeState> {
  const out = {} as Record<DeploymentName, NodeState>
  for (const name of DEPLOYMENTS) {
    const d = s.deployments.find((x) => x.name === name)
    const pods = s.pods.filter((p) => p.service === name)
    const svcName = name.replace(/-worker$/, '')
    const svc = name.endsWith('-worker') || name === 'web' ? undefined : s.services.find((x) => x.name === svcName)
    const build = s.services.find((x) => x.name === svcName)
    const version = known(build?.version)
    const commit = shortCommit(build?.commit)
    // web has no healthz build: its pods' image tags say what runs (two while rolling out)
    const tags = name === 'web' ? [...new Set(pods.map((p) => p.image_tag).filter((x): x is string => !!x))] : []
    const restarts = pods.reduce((n, p) => n + p.restarts, 0)
    const before = previous?.pods.filter((p) => p.service === name).reduce((n, p) => n + p.restarts, 0)
    const rolling = d ? (d.progressing ?? d.updated < d.replicas) || new Set(pods.map((p) => p.image_tag)).size > 1 : false
    const reasons: Reason[] = []
    if (pods.some((p) => p.reason && FAILED.test(p.reason))) reasons.push('crash')
    if (before !== undefined && restarts > before) reasons.push('climbing')
    if (d && d.replicas > 0 && d.ready === 0 && !rolling) reasons.push('notReady')
    if (svc && !svc.healthy) reasons.push('noAnswer')
    if (rolling) reasons.push('rolling')
    else if (d && d.ready > 0 && d.ready < d.replicas) reasons.push('partly')
    if (restarts > 0 && !reasons.includes('climbing')) reasons.push('restarts')
    let state: NodeHealth
    if (reasons.some((r) => DOWN.has(r))) state = 'down'
    else if (reasons.length > 0) state = 'warn'
    else if (d || svc?.healthy) state = 'ok'
    else state = 'unknown'
    out[name] = { replicas: d ? `${d.ready}/${d.replicas}` : null, build: name === 'web' ? tags.join(' / ') || null : [version, commit].filter(Boolean).join(' · ') || null, state, restarts, reasons }
  }
  return out
}

/** An external service's colour from what the API services' healthz say
 *  about it: red when one reports it down, green when some report it and
 *  all say ok, grey (not probed) when none does. */
export function dependencyState(s: SystemInfo, dep: Dependency): NodeHealth {
  const said = s.services.map((x) => x.dependencies?.[dep]).filter((v): v is 'ok' | 'down' => v !== undefined)
  if (said.length === 0) return 'unknown'
  return said.includes('down') ? 'down' : 'ok'
}

/** Days before the certificate's end from which the ingress box is amber. */
export const TLS_WARN_DAYS = 14

/** The ingress box from the account service's outside probe: red when the
 *  public URL does not answer, amber when the certificate ends within
 *  `TLS_WARN_DAYS`, green otherwise, grey without a probe. `line` is
 *  "TLS until 2027-01-12". */
export function ingressState(s: SystemInfo, now: Date = new Date()): { state: NodeHealth; line: string | null; expiresSoon: boolean } {
  const ing = s.ingress
  if (!ing) return { state: 'unknown', line: null, expiresSoon: false }
  const ends = ing.tls_expires_at ? new Date(ing.tls_expires_at) : null
  const expiresSoon = ends !== null && !Number.isNaN(ends.getTime()) && ends.getTime() - now.getTime() < TLS_WARN_DAYS * 86_400_000
  const state: NodeHealth = ing.status === 'down' ? 'down' : expiresSoon ? 'warn' : 'ok'
  return { state, line: ing.tls_expires_at ? ing.tls_expires_at.slice(0, 10) : null, expiresSoon }
}
