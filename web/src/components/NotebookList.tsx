import { useState, type FormEvent } from 'react'
import type { Notebook } from '../api/types'
import { t } from '../i18n'
import { renamedTitle } from '../lib/conversations'
import { InlineRename } from './InlineRename'
import { NotebookShareCard } from './ShareCard'

/** ingest's limit for a notebook title */
const NOTEBOOK_TITLE_MAX = 200

interface Props {
  notebooks: Notebook[]
  selectedId: string | null
  onSelect: (id: string) => void
  onCreate: (title: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
  /** a double-click (or F2) on a notebook renames it */
  onRename: (id: string, title: string) => void
  /** the notebook's read-only link changed (created or revoked) */
  onShared: (id: string, shareToken: string | null) => void
  /** the starter notebook every new account gets a copy of, marked "Starter" */
  starterId?: string | null
  /** admins only: make this notebook the starter */
  onMakeStarter?: (id: string) => void
}

export function NotebookList({ notebooks, selectedId, onSelect, onCreate, onDelete, onRename, onShared, starterId = null, onMakeStarter }: Props) {
  const [title, setTitle] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  // the notebook whose share card is open
  const [sharing, setSharing] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const name = title.trim()
    if (!name) return
    await onCreate(name)
    setTitle('')
  }

  return (
    <section className="notebooks">
      <form onSubmit={submit} className="row">
        <input placeholder={t('nb.new')} value={title} onChange={(e) => setTitle(e.target.value)} />
        <button type="submit" disabled={!title.trim()}>
          {t('common.add')}
        </button>
      </form>
      <ul className="list">
        {notebooks.map((nb) => (
          <li key={nb.id} className={nb.id === selectedId ? 'selected' : undefined}>
            {editing === nb.id ? (
              <InlineRename
                className="item-edit"
                value={nb.title}
                label={t('nb.renameLabel')}
                maxLength={NOTEBOOK_TITLE_MAX}
                onCancel={() => setEditing(null)}
                onCommit={(draft) => {
                  setEditing(null)
                  const next = renamedTitle(draft, nb.title)
                  if (next) onRename(nb.id, next)
                }}
              />
            ) : (
              <span className="nb-name">
                <button
                  type="button"
                  className="item"
                  title={`${nb.title} · ${t('nb.renameHint')}`}
                  onClick={() => onSelect(nb.id)}
                  onDoubleClick={() => setEditing(nb.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'F2') {
                      e.preventDefault()
                      setEditing(nb.id)
                    }
                  }}
                >
                  {nb.title}
                </button>
                {nb.id === starterId && (
                  <span className="badge starter" title={t('starter.listTitle')}>
                    {t('starter.badge')}
                  </span>
                )}
              </span>
            )}
            {/* the icons stay together: the row wraps only as a group, below the name */}
            <span className="nb-actions">
              {onMakeStarter && nb.id !== starterId && (
                <button type="button" className="icon" title={t('starter.use')} aria-label={t('starter.use')} onClick={() => onMakeStarter(nb.id)}>
                  ☆
                </button>
              )}
              <button
                type="button"
                className={nb.share_token ? 'icon share-toggle shared' : 'icon share-toggle'}
                title={nb.share_token ? t('nbShare.sharedTitle') : t('nbShare.share')}
                aria-label={nb.share_token ? t('nbShare.sharedTitle') : t('nbShare.share')}
                aria-expanded={sharing === nb.id}
                onClick={() => setSharing((s) => (s === nb.id ? null : nb.id))}
              >
                ⤴
              </button>
              <button
                type="button"
                className="icon"
                title={t('nb.delete')}
                onClick={() => void onDelete(nb.id)}
              >
                ×
              </button>
            </span>
            {sharing === nb.id && (
              <div className="nb-share">
                <NotebookShareCard notebook={nb} onChanged={(token) => onShared(nb.id, token)} />
              </div>
            )}
          </li>
        ))}
        {notebooks.length === 0 && <li className="muted">{t('nb.none')}</li>}
      </ul>
    </section>
  )
}
