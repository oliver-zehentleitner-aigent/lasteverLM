import type { OutputPhase } from '../api/types'
import { t } from '../i18n'

/** "1:42" since `iso`, "1:02:05" past an hour; never negative. Pure, so it is tested. */
export function elapsedLabel(iso: string, now: number): string | null {
  const start = new Date(iso).getTime()
  if (Number.isNaN(start)) return null
  const s = Math.max(0, Math.floor((now - start) / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

/** The phase as a line: "Judging, round 2 of 3", "Reading the sources:
 *  a.pdf, b.pdf", "Attempt 2 of 3 follows (glm-5.3: timeout)". Only what the
 *  worker sent; a step the web does not know shows by its name. Pure, so
 *  it is tested. */
export function phaseLabel(p: OutputPhase): string {
  switch (p.step) {
    case 'waiting_for_sources':
      return p.sources && p.sources.length > 0 ? t('phase.waitingFor', { names: p.sources.join(', ') }) : t('phase.waiting_for_sources')
    case 'judging':
      return p.n != null && p.of != null ? t('phase.judgingN', { n: p.n, of: p.of }) : t('phase.judging')
    case 'revising':
      return p.n != null ? t('phase.revisingN', { n: p.n }) : t('phase.revising')
    case 'synthesizing_speech':
      return p.n != null && p.of != null ? t('phase.speechN', { n: p.n, of: p.of }) : t('phase.synthesizing_speech')
    case 'retry':
      if (p.n == null || p.of == null) return t('phase.retry')
      return p.error ? t('phase.retryN', { n: p.n, of: p.of, error: p.error }) : t('phase.retryOnly', { n: p.n, of: p.of })
    case 'retrieving':
    case 'deciding':
    case 'writing':
    case 'checking':
    case 'indexing':
      return t(`phase.${p.step}`)
    default:
      return (p as { step: string }).step
  }
}
