import type { Source } from '../api/types'
import { t } from '../i18n'

/** Selected sources that cannot be read, from rag's estimate: each with
 *  the reason and the way out, turning it off for this action, or, for a
 *  web page, fetching it again (which may clear the reason). */
export function BlockedSources({
  blocked,
  webPages,
  refresh,
  onDeselect,
  onRefetch,
}: {
  blocked: readonly { library_id: string; name: string; reason: string }[]
  webPages: readonly Source[]
  refresh: ReadonlySet<string>
  onDeselect: (libraryId: string) => void
  onRefetch: (libraryId: string) => void
}) {
  if (blocked.length === 0) return null
  return (
    <ul className="blocked-sources small" role="status">
      {blocked.map((b) => {
        const page = webPages.some((s) => (s.library_id ?? s.id) === b.library_id)
        return (
          <li key={b.library_id}>
            <span className="error">{b.reason}</span>{' '}
            <button type="button" className="link" onClick={() => onDeselect(b.library_id)}>
              {t('blocked.deselect')}
            </button>
            {page && !refresh.has(b.library_id) && (
              <>
                {' · '}
                <button type="button" className="link" onClick={() => onRefetch(b.library_id)}>
                  {t('blocked.refetch')}
                </button>
              </>
            )}
          </li>
        )
      })}
    </ul>
  )
}
