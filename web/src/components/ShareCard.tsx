import { rag } from '../api/rag'
import type { Output } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { t } from '../i18n'

/** An output's read-only link: create it, or copy and revoke it. Used by
 *  the viewer and by the library's output rows. */
export function ShareCard({ output, onChanged }: { output: Pick<Output, 'id' | 'share_token'>; onChanged: (shareToken: string | null) => void }) {
  const { busy, error, run } = useAsync()
  const shareUrl = output.share_token ? `${window.location.origin}/s/${output.share_token}` : null

  async function share() {
    const r = await run(() => rag.share(output.id))
    if (r) onChanged(r.share_token)
  }
  async function unshare() {
    if (await run(() => rag.unshare(output.id).then(() => true))) onChanged(null)
  }

  return (
    <div className="share card no-print">
      {shareUrl ? (
        <>
          <p className="small">{t('viewer.shareInfo')}</p>
          <div className="row">
            <input readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} />
            <button type="button" className="secondary" onClick={() => void navigator.clipboard?.writeText(shareUrl)}>
              {t('viewer.copy')}
            </button>
            <button type="button" className="secondary" disabled={busy} onClick={() => void unshare()}>
              {t('viewer.revoke')}
            </button>
          </div>
        </>
      ) : (
        <div className="row">
          <p className="small">{t('viewer.shareCreateInfo')}</p>
          <button type="button" disabled={busy} onClick={() => void share()}>
            {t('viewer.createLink')}
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
