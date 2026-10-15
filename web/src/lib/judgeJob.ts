import { ApiError } from '../api/client'
import type { JudgeJob } from '../api/types'
import { t } from '../i18n'

/** how often a running judgement is asked for */
export const JUDGE_POLL_MS = 2000

/** Whether the job still runs: it is polled while it does. */
export const jobActive = (job: JudgeJob | null | undefined): boolean => !!job && (job.status === 'queued' || job.status === 'running')

/** What the user reads while a judgement runs or after it failed:
 *  "Waiting for the judge…", "Judging, paragraph 4 of 11" (claim, for an
 *  output), "The judge failed: <reason>"; null once it is done. Pure, so it
 *  is tested. */
export function jobLine(job: JudgeJob): string | null {
  if (job.status === 'queued') return t('judge.job.queued')
  if (job.status === 'running') {
    if (!job.phase || job.phase.of <= 0) return t('judge.job.running')
    return t(job.target === 'message' ? 'judge.job.paragraph' : 'judge.job.claim', { n: Math.min(job.phase.n + 1, job.phase.of), of: job.phase.of })
  }
  if (job.status === 'failed') return t('judge.job.failed', { error: job.error?.trim() || t('judge.job.noReason') })
  return null
}

/** The job a 409 "a judgement is already running" names: polled instead
 *  of starting another. */
export function runningJobId(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null
  const id = (err.body as { job_id?: unknown } | null)?.job_id
  return typeof id === 'string' && id ? id : null
}
