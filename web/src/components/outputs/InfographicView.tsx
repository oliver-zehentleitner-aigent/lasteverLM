import type { InfographicContent } from '../../api/types'
import { ClaimMarks } from '../OutputProvenance'

/** Card grid: the headline, one card per fact, one card per section; each
 *  fact and section with its passage markers when it has provenance. */
export function InfographicView({ content }: { content: InfographicContent }) {
  return (
    <div className="infographic">
      <h2 className="headline">{content.headline}</h2>
      <div className="facts">
        {(content.facts ?? []).map((f, i) => (
          <div key={i} className="fact">
            <div className="value">{f.value}</div>
            <div className="label muted">{f.label}</div>
            <div className="marks">
              <ClaimMarks claim={f} text={`${f.value} ${f.label}`} />
            </div>
          </div>
        ))}
      </div>
      <div className="sections">
        {(content.sections ?? []).map((s, i) => (
          <section key={i} className="card">
            <h3>{s.title}</h3>
            <p>
              {s.text} <ClaimMarks claim={s} text={s.text} />
            </p>
          </section>
        ))}
      </div>
    </div>
  )
}
