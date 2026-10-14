import { useState, type FormEvent } from 'react'
import type { Notebook } from '../api/types'
import { t } from '../i18n'

interface Props {
  notebooks: Notebook[]
  selectedId: string | null
  onSelect: (id: string) => void
  onCreate: (title: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
}

export function NotebookList({ notebooks, selectedId, onSelect, onCreate, onDelete }: Props) {
  const [title, setTitle] = useState('')

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
            <button type="button" className="item" onClick={() => onSelect(nb.id)}>
              {nb.title}
            </button>
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
