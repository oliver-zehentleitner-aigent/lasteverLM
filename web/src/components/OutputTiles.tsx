import type { OutputKind } from '../api/types'
import { OUTPUT_FORMS, tileNote } from '../lib/outputs'

interface Props {
  disabled: boolean
  onCreate: (kind: OutputKind) => void
}

/** The output forms as tiles under the sources. A click asks rag to
 *  generate one; the result appears as a tab in the viewer. */
export function OutputTiles({ disabled, onCreate }: Props) {
  return (
    <section className="tiles">
      <h2>Create</h2>
      <div className="tile-grid">
        {OUTPUT_FORMS.map((f) => (
          <button
            key={f.kind}
            type="button"
            className="tile"
            disabled={disabled || !f.available}
            title={tileNote(f)}
            onClick={() => onCreate(f.kind)}
          >
            <strong>{f.label}</strong>
            <span className="muted small">{tileNote(f)}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
