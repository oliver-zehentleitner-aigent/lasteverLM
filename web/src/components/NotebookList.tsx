import { useState, type FormEvent } from 'react'
import type { Notebook } from '../api/types'

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
    const t = title.trim()
    if (!t) return
    await onCreate(t)
    setTitle('')
  }

  return (
    <section className="notebooks">
      <form onSubmit={submit} className="row">
        <input placeholder="New notebook…" value={title} onChange={(e) => setTitle(e.target.value)} />
        <button type="submit" disabled={!title.trim()}>
          Add
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
              title="Delete notebook"
              onClick={() => {
                if (confirm(`Delete notebook "${nb.title}"? Its chats and generated documents are deleted; its sources stay in your library.`)) void onDelete(nb.id)
              }}
            >
              ×
            </button>
          </li>
        ))}
        {notebooks.length === 0 && <li className="muted">No notebooks yet.</li>}
      </ul>
    </section>
  )
}
