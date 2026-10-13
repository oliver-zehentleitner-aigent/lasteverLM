import type { OutputKind } from '../api/types'
import { OUTPUT_FORMS, createBlocker, tileNote } from '../lib/outputs'

interface Props {
  selected: OutputKind | null
  hasReadySource: boolean
  busy: boolean
  onSelect: (kind: OutputKind) => void
  onCreate: (kind: OutputKind) => void
}

/** The output formats as tiles under the sources. A click (or Enter on a
 *  focused tile) only selects one; the Create button below starts the job
 *  for the selected format, and says why when it cannot yet. */
export function OutputTiles({ selected, hasReadySource, busy, onSelect, onCreate }: Props) {
  const blocker = createBlocker(selected, hasReadySource)
  return (
    <section className="tiles">
      <h2>Output format</h2>
      <div className="tile-grid" role="radiogroup" aria-label="Output format">
        {OUTPUT_FORMS.map((f) => (
          <button
            key={f.kind}
            type="button"
            role="radio"
            aria-checked={f.kind === selected}
            className={f.kind === selected ? 'tile selected' : 'tile'}
            disabled={!f.available}
            title={tileNote(f)}
            onClick={() => onSelect(f.kind)}
          >
            <strong>{f.label}</strong>
            <span className="muted small">{tileNote(f)}</span>
          </button>
        ))}
      </div>
      <div className="create-row">
        {blocker && <span className="muted small">{blocker}</span>}
        <button type="button" disabled={busy || blocker !== null} onClick={() => selected && onCreate(selected)}>
          Create
        </button>
      </div>
    </section>
  )
}
