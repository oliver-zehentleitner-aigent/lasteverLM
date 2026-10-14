import { useState } from 'react'
import type { JudgeLevel } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { useEstimate } from '../hooks/useEstimate'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { t } from '../i18n'
import { PriceTag } from './PriceTag'

type Level = Exclude<JudgeLevel, 'off'>

/** "Check with a judge" on something that exists already (an output, a
 *  chat answer): a level, its one-line explanation, and Check, which
 *  annotates every claim and removes nothing. One billed call; a 402
 *  opens the voucher dialog as everywhere. The level's estimated charge
 *  stands next to Check; `subject` is what the estimate needs of the
 *  judged thing (an output's kind and a quiz's question count), left out
 *  for a chat answer. */
export function JudgeRequest({
  onJudge,
  subject,
  compact = false,
}: {
  onJudge: (level: Level) => Promise<unknown>
  subject?: { kind: string; question_count?: number }
  compact?: boolean
}) {
  const spec = useOutputOptions()
  const levels = (spec?.judge?.levels ?? ['low', 'medium', 'high']).filter((l): l is Level => l !== 'off')
  const [open, setOpen] = useState(false)
  const [level, setLevel] = useState<Level>('medium')
  const { busy, error, run } = useAsync()
  const price = useEstimate(open ? { action: 'judge', options: { ...subject, level } } : null, 0)

  if (!open)
    return (
      <button type="button" className="link small" title={t('judge.runTitle')} onClick={() => setOpen(true)}>
        {t('judge.label')}
      </button>
    )
  return (
    <span className={compact ? 'judge-request compact' : 'judge-request'}>
      <select value={level} aria-label={t('judge.label')} onChange={(e) => setLevel(e.target.value as Level)}>
        {levels.map((l) => (
          <option key={l} value={l}>
            {t(`judge.level.${l}`)}
            {spec?.judge?.models[l] ? ` (${spec.judge.models[l]})` : ''}
          </option>
        ))}
      </select>
      <button type="button" className="secondary small" disabled={busy} title={t('judge.runTitle')} onClick={() => void run(async () => (await onJudge(level), true)).then((ok) => ok && setOpen(false))}>
        {busy ? t('judge.running') : t('judge.run')}
      </button>
      <PriceTag state={price} />
      <button type="button" className="icon" aria-label={t('common.close')} onClick={() => setOpen(false)}>
        ×
      </button>
      <span className="muted small">{t(`judge.explain.${level}`)}</span>
      {error && <span className="error small">{error}</span>}
    </span>
  )
}
