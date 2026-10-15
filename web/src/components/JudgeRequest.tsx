import { useEffect, useRef, useState } from 'react'
import { rag } from '../api/rag'
import type { JudgeJob, JudgeLevel } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useEstimate } from '../hooks/useEstimate'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { t } from '../i18n'
import { PriceTag } from './PriceTag'
import { JUDGE_ASK_LEVEL } from '../lib/judge'
import { JUDGE_POLL_MS, jobActive, jobLine, runningJobId } from '../lib/judgeJob'
import { OutputId } from './OutputId'
import { requestBalanceRefresh, useBalanceActivity } from '../lib/balance'

type Level = Exclude<JudgeLevel, 'off'>

/** "Check with a judge" on something that exists already (an output, a
 *  chat answer): a level, its one-line explanation, and Check, which
 *  annotates every claim and removes nothing. One billed call; a 402
 *  opens the voucher dialog as everywhere. The level's estimated charge
 *  stands next to Check; `subject` is what the estimate needs of the
 *  judged thing (an output's kind, a quiz's question count, the flashcards'
 *  card count), left out
 *  for a chat answer. `opened` (a counter) opens it from outside, as
 *  "Have it judged" does, and focuses the level so it scrolls into view.
 *  Check starts a background job: while it runs the control says where
 *  it is ("Judging, claim 4 of 11", polled every 2 s; one already
 *  running, found on opening or named by a 409, is followed the same
 *  way), when it is done `onDone` reloads the target with its verdicts,
 *  and a failure says why, with the output's ID. */
export function JudgeRequest({
  target,
  onDone,
  subject,
  compact = false,
  opened = 0,
}: {
  /** what is judged: `start` asks for a judgement, the id finds a running one */
  target: { kind: 'output' | 'message'; id: string; start: (level: Level) => Promise<JudgeJob> }
  /** the job is done: reload the target, its verdicts are on it */
  onDone: () => Promise<unknown> | void
  subject?: { kind: string; question_count?: number; card_count?: number }
  compact?: boolean
  opened?: number
}) {
  const spec = useOutputOptions()
  const levels = (spec?.judge?.levels ?? ['low', 'medium', 'high']).filter((l): l is Level => l !== 'off')
  const [open, setOpen] = useState(false)
  const [level, setLevel] = useState<Level>(JUDGE_ASK_LEVEL)
  const select = useRef<HTMLSelectElement>(null)
  // opened from outside: open, then focus the level once it is there
  const [seen, setSeen] = useState(opened)
  if (opened !== seen) {
    setSeen(opened)
    if (opened > 0) setOpen(true)
  }
  useEffect(() => {
    if (opened > 0) select.current?.focus()
  }, [opened])
  const { busy, error, run } = useAsync()
  const price = useEstimate(open ? { action: 'judge', options: { ...subject, level } } : null, 0)
  const [job, setJob] = useState<JudgeJob | null>(null)
  const done = useRef(onDone)
  useEffect(() => {
    done.current = onDone
  }, [onDone])

  // a judgement already running when this opens (a reload, another tab) is followed
  useEffect(() => {
    let live = true
    rag.latestJudgeJob(target.kind, target.id).then(
      (j) => live && jobActive(j) && setJob(j),
      () => {
        // none to follow; Check still works
      },
    )
    return () => {
      live = false
    }
  }, [target.kind, target.id])

  // while it runs: ask again every 2 s; done reloads the target and clears the line
  const activeId = jobActive(job) ? job!.job_id : null
  // a judgement is paid work: the balance follows while it runs and when it ends
  useBalanceActivity(activeId !== null)
  useEffect(() => {
    if (activeId === null) return
    let live = true
    let timer = 0
    const poll = () => {
      timer = window.setTimeout(() => {
        rag.getJudgeJob(activeId).then(
          (next) => {
            if (!live) return
            if (next.status === 'done') {
              setJob(null)
              requestBalanceRefresh()
              void done.current()
            } else {
              if (next.status === 'failed') requestBalanceRefresh()
              setJob(next)
              if (jobActive(next)) poll()
            }
          },
          () => live && poll(),
        )
      }, JUDGE_POLL_MS)
    }
    poll()
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [activeId])

  async function check() {
    const started = await run(async () => {
      try {
        return await target.start(level)
      } catch (err) {
        // one is running already: follow that one
        const id = runningJobId(err)
        if (id) return rag.getJudgeJob(id)
        throw err
      }
    })
    if (started) {
      setJob(started)
      setOpen(false)
    }
  }

  if (job) {
    const line = jobLine(job)
    return (
      <span className={job.status === 'failed' ? 'judge-job failed' : 'judge-job'} role="status" aria-live="polite">
        {job.status !== 'failed' && <span className="spinner" aria-hidden="true" />}
        <span className={job.status === 'failed' ? 'error small' : 'muted small'}>{line}</span>
        {job.status === 'failed' && (
          <>
            {job.attempts > 1 && <span className="muted small"> · {t('judge.job.attempts', { n: job.attempts })}</span>}
            {target.kind === 'output' && <OutputId id={target.id} />}
            <button type="button" className="icon" aria-label={t('common.close')} title={t('common.close')} onClick={() => setJob(null)}>
              ×
            </button>
          </>
        )}
      </span>
    )
  }

  if (!open)
    return (
      <button type="button" className="link small" title={t('judge.runTitle')} onClick={() => setOpen(true)}>
        {t('judge.label')}
      </button>
    )
  return (
    <span className={compact ? 'judge-request compact' : 'judge-request'}>
      <select ref={select} value={level} aria-label={t('judge.label')} onChange={(e) => setLevel(e.target.value as Level)}>
        {levels.map((l) => (
          <option key={l} value={l}>
            {t(`judge.level.${l}`)}
            {spec?.judge?.models[l] ? ` (${spec.judge.models[l]})` : ''}
          </option>
        ))}
      </select>
      <button type="button" className="secondary small" disabled={busy} title={t('judge.runTitle')} onClick={() => void check()}>
        {busy ? t('judge.running') : t('judge.run')}
      </button>
      <PriceTag state={price} />
      <button type="button" className="icon" aria-label={t('common.close')} onClick={() => setOpen(false)}>
        ×
      </button>
      <span className="muted small">{t(`judge.onRequest.${level}`)}</span>
      {error && <span className="error small">{error}</span>}
    </span>
  )
}
