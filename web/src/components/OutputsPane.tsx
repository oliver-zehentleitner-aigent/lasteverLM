import type { Output } from '../api/types'
import { formFor } from '../lib/outputs'
import { t } from '../i18n'

interface Props {
  outputs: Output[]
  selectedId: string | null
  onOpen: (id: string) => void
  onDelete: (o: Output) => void
}

/** Left column, under Create: the generated documents with kind, title and
 *  status. A click opens the document's tab in the viewer; × deletes it,
 *  the same as the viewer's delete action. */
export function OutputsPane({ outputs, selectedId, onOpen, onDelete }: Props) {
  return (
    <section className="pane outputs">
      <h2>{t('outputs.title')}</h2>
      <ul className="list">
        {outputs.map((o) => (
          <li key={o.id} id={`output-${o.id}`} className={o.id === selectedId ? 'selected' : ''}>
            <button type="button" className="item" onClick={() => onOpen(o.id)} title={o.title || formFor(o.kind).label}>
              <span className="badge">{formFor(o.kind).label}</span>
              <span className="name">{o.title || formFor(o.kind).label}</span>
              <span className={`badge ${o.status}`}>{t(`status.${o.status}`)}</span>
            </button>
            <button type="button" className="icon" title={t('outputs.delete')} onClick={() => onDelete(o)}>
              ×
            </button>
          </li>
        ))}
        {outputs.length === 0 && <li className="muted small">{t('outputs.none')}</li>}
      </ul>
    </section>
  )
}
