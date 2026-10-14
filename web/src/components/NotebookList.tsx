import { useState, type FormEvent } from 'react'
import type { Notebook } from '../api/types'
import { t } from '../i18n'
import { renamedTitle } from '../lib/conversations'
import { InlineRename } from './InlineRename'

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
}

export function NotebookList({ notebooks, selectedId, onSelect, onCreate, onDelete, onRename }: Props) {
  const [title, setTitle] = useState('')
  const [editing, setEditing] = useState<string | null>(null)

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
              <button
                type="button"
                className="item"
                title={t('nb.renameHint')}
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
            )}
            <button
              type="button"
              className="icon"
              title={t('nb.delete')}
              onClick={() => void onDelete(nb.id)}
            >
              ×
            </button>
          </li>
        ))}
        {notebooks.length === 0 && <li className="muted">{t('nb.none')}</li>}
      </ul>
    </section>
  )
}
