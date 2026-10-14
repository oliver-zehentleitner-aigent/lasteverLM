import { admin } from '../../api/admin'
import type { FeedbackStats } from '../../api/types'
import { useLoad } from '../../hooks/useLoad'
import { t } from '../../i18n'
import { formatTime } from '../../lib/format'

const DAYS = 30
// module level: useLoad reloads whenever its function changes
const loadFeedback = () => admin.feedback(DAYS)

/** The overview's answer feedback: thumbs up and down over the last 30
 *  days, and the newest down-rated answers (question, answer, comment)
 *  folded under it; a viewer sees the counts, the list is for admins. */
export function FeedbackSummary() {
  const { data, error } = useLoad<FeedbackStats | null>(loadFeedback, null)
  if (error) return <p className="error small">{error}</p>
  if (!data) return null
  const up = data.days.reduce((n, d) => n + d.up, 0)
  const down = data.days.reduce((n, d) => n + d.down, 0)
  return (
    <details className="feedback-summary card">
      <summary>
        {t('fb.title', { days: DAYS })}: <strong>{t('fb.counts', { up, down })}</strong>
      </summary>
      <h3 className="small">{t('fb.latest')}</h3>
      {data.detail ? (
        <p className="muted small">{t('fb.adminsOnly')}</p>
      ) : data.latest_down.length === 0 ? (
        <p className="muted small">{t('fb.none')}</p>
      ) : (
        <ul className="feedback-list">
          {data.latest_down.map((f) => (
            <li key={f.message_id}>
              <span className="muted small">{formatTime(f.at)}</span>
              {f.question && (
                <p>
                  <strong>{t('fb.question')}:</strong> {f.question}
                </p>
              )}
              <p className="feedback-answer">
                <strong>{t('fb.answer')}:</strong> {f.answer}
              </p>
              {f.comment && (
                <p>
                  <strong>{t('fb.comment')}:</strong> {f.comment}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </details>
  )
}
