import { useState } from 'react'
import { rag } from '../api/rag'
import { useAsync } from '../hooks/useAsync'
import { useEstimate } from '../hooks/useEstimate'
import { t } from '../i18n'
import { SuggestionCards } from './AnswerActions'
import { PriceTag } from './PriceTag'

/** An empty chat's way in: "Suggest questions" with its price, then the
 *  notebook's questions as cards. Asked on a click, not on its own: the
 *  first call is billed (later ones come from rag's cache until the
 *  sources change). */
export function StarterQuestions({ notebookId, disabled, onAsk }: { notebookId: string; disabled: boolean; onAsk: (q: string) => void }) {
  const [found, setFound] = useState<string[] | null>(null)
  const { busy, error, run } = useAsync()
  const price = useEstimate(found === null ? { action: 'chat_answer', options: { suggestions: true } } : null)

  async function load() {
    const r = await run(() => rag.notebookSuggestions(notebookId))
    if (r) setFound(r.suggestions)
  }

  if (found !== null)
    return found.length > 0 ? <SuggestionCards suggestions={found} disabled={disabled} onAsk={onAsk} /> : <p className="muted small">{t('chat.noSuggestions')}</p>
  return (
    <p className="starter-questions no-print">
      <button type="button" className="secondary small" disabled={busy} onClick={() => void load()}>
        {busy ? t('common.loading') : t('chat.suggest')}
      </button>{' '}
      <PriceTag state={price} />
      {error && <span className="error small"> {error}</span>}
    </p>
  )
}
