import type { InfographicContent } from '../../api/types'
import { ClaimMarks } from '../OutputProvenance'

/** An infographic: one card grid, or, made from proposed themes, one per
 *  theme under its title. */
export function InfographicView({ content }: { content: InfographicContent }) {
  if (!content.parts?.length) return <OneInfographic content={content} />
  return (
    <div className="infographic-parts">
      {content.parts.map((part) => (
        <section key={part.candidate_id} className="infographic-part">
          <h3 className="part-title">{part.title}</h3>
          <OneInfographic content={part} />
        </section>
      ))}
    </div>
  )
}

/** Card grid: the headline, one card per fact, one card per section; each
 *  fact and section with its passage markers when it has provenance. */
function OneInfographic({ content }: { content: InfographicContent }) {
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
