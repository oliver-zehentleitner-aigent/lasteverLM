import type { Source } from '../api/types'
import { t } from '../i18n'
import { whenLabel } from '../lib/outputsList'

/** The selected web pages, each with its own choice: the cached version
 *  (when it was fetched) or fetch again first. Cached by default; the
 *  chosen ones go to rag as `url_refresh` (library ids). */
export function UrlRefresh({ pages, refresh, onChange }: { pages: readonly Source[]; refresh: ReadonlySet<string>; onChange: (next: Set<string>) => void }) {
  if (pages.length === 0) return null
  const id = (s: Source) => s.library_id ?? s.id
  return (
    <div className="url-refresh small">
      <span className="muted">{t('urlRefresh.title')}</span>
      <ul>
        {pages.map((s) => {
          const again = refresh.has(id(s))
          const set = (on: boolean) => {
            const next = new Set(refresh)
            if (on) next.add(id(s))
            else next.delete(id(s))
            onChange(next)
          }
          return (
            <li key={s.id}>
              <span className="url-refresh-name" title={s.name}>
                {s.name}
              </span>
              <span className="presets" role="radiogroup" aria-label={t('urlRefresh.choice', { name: s.name })}>
                <button type="button" role="radio" aria-checked={!again} className={again ? 'preset' : 'preset active'} onClick={() => set(false)}>
                  {s.fetched_at ? t('urlRefresh.cachedAt', { when: whenLabel(s.fetched_at) }) : t('urlRefresh.cached')}
                </button>
                <button type="button" role="radio" aria-checked={again} className={again ? 'preset active' : 'preset'} onClick={() => set(true)}>
                  {t('urlRefresh.again')}
                </button>
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
