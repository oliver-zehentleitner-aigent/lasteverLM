import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import type { JudgeJob } from '../api/types'
import { jobActive, jobLine, runningJobId } from './judgeJob'

const job = (o: Partial<JudgeJob>): JudgeJob => ({
  job_id: 'j1',
  target: 'output',
  target_id: 'o1',
  level: 'medium',
  status: 'running',
  phase: null,
  attempts: 1,
  attempt_log: [],
  error: null,
  created_at: 'now',
  finished_at: null,
  ...o,
})

describe('judge jobs', () => {
  it('runs while queued or running', () => {
    expect(jobActive(job({ status: 'queued' }))).toBe(true)
    expect(jobActive(job({ status: 'running' }))).toBe(true)
    expect(jobActive(job({ status: 'done' }))).toBe(false)
    expect(jobActive(null)).toBe(false)
  })
  it('says where it is: waiting, the claim or paragraph being judged, or why it failed', () => {
    expect(jobLine(job({ status: 'queued' }))).toBe('Waiting for the judge…')
    expect(jobLine(job({ phase: { step: 'judging', n: 3, of: 11 } }))).toBe('Judging, claim 4 of 11')
    expect(jobLine(job({ target: 'message', phase: { step: 'judging', n: 3, of: 11 } }))).toBe('Judging, paragraph 4 of 11')
    expect(jobLine(job({ phase: { step: 'judging', n: 11, of: 11 } }))).toBe('Judging, claim 11 of 11')
    expect(jobLine(job({}))).toBe('Judging…')
    expect(jobLine(job({ status: 'failed', error: 'the model did not answer' }))).toBe('The judge failed: the model did not answer')
    expect(jobLine(job({ status: 'done' }))).toBeNull()
  })
  it("resumes the job a 409 names instead of starting another", () => {
    expect(runningJobId(new ApiError(409, 'x', null, { error: 'a judgement is already running', job_id: 'j9' }))).toBe('j9')
    expect(runningJobId(new ApiError(409, 'x', null, { error: 'other' }))).toBeNull()
    expect(runningJobId(new ApiError(402, 'x'))).toBeNull()
  })
})
