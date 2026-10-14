import { ingest } from '../api/ingest'
import { rag } from '../api/rag'
import type { Output } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { t } from '../i18n'

interface LinkProps {
  /** the public link, or null while there is none */
  url: string | null
  onCreate: () => Promise<string | null | undefined>
  onRevoke: () => Promise<boolean | undefined>
  info: string
  createInfo: string
}

/** A read-only link: create it, or copy and revoke it. */
function LinkCard({ url, onCreate, onRevoke, info, createInfo }: LinkProps) {
  const { busy, error, run } = useAsync()
  return (
    <div className="share card no-print">
      {url ? (
        <>
          <p className="small">{info}</p>
          <div className="row">
            <input readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
            <button type="button" className="secondary" onClick={() => void navigator.clipboard?.writeText(url)}>
              {t('viewer.copy')}
            </button>
            <button type="button" className="secondary" disabled={busy} onClick={() => void run(onRevoke)}>
              {t('viewer.revoke')}
            </button>
          </div>
        </>
      ) : (
        <div className="row">
          <p className="small">{createInfo}</p>
          <button type="button" disabled={busy} onClick={() => void run(onCreate)}>
            {t('viewer.createLink')}
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}

/** An output's read-only link (`/s/<token>`). Used by the viewer and by
 *  the library's output rows. */
export function ShareCard({ output, onChanged }: { output: Pick<Output, 'id' | 'share_token'>; onChanged: (shareToken: string | null) => void }) {
  return (
    <LinkCard
      url={output.share_token ? `${window.location.origin}/s/${output.share_token}` : null}
      info={t('viewer.shareInfo')}
      createInfo={t('viewer.shareCreateInfo')}
      onCreate={async () => {
        const r = await rag.share(output.id)
        onChanged(r.share_token)
        return r.share_token
      }}
      onRevoke={async () => {
        await rag.unshare(output.id)
        onChanged(null)
        return true
      }}
    />
  )
}

/** A notebook's read-only link (`/shared/notebook/<token>`): its title,
 *  its sources by name and its outputs, no source files. */
export function NotebookShareCard({ notebook, onChanged }: { notebook: { id: string; share_token?: string | null }; onChanged: (shareToken: string | null) => void }) {
  return (
    <LinkCard
      url={notebook.share_token ? `${window.location.origin}/shared/notebook/${notebook.share_token}` : null}
      info={t('nbShare.info')}
      createInfo={t('nbShare.createInfo')}
      onCreate={async () => {
        const r = await ingest.shareNotebook(notebook.id)
        onChanged(r.share_token)
        return r.share_token
      }}
      onRevoke={async () => {
        await ingest.unshareNotebook(notebook.id)
        onChanged(null)
        return true
      }}
    />
  )
}
