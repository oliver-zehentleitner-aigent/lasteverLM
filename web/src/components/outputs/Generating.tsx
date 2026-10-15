import { useEffect, useState } from 'react'
import type { OutputKind, OutputPhase } from '../../api/types'
import { elapsedLabel, phaseLabel } from '../../lib/generating'
import { OutputId } from '../OutputId'

/** The skeleton's shape per kind; kinds where a shape adds nothing share the lines. */
const SHAPE: Partial<Record<OutputKind, string>> = {
  report: 'lines',
  table: 'grid',
  mindmap: 'nodes',
  audio: 'wave',
  flashcards: 'card',
  quiz: 'quiz',
  chart: 'bars',
  decision: 'scale',
  infographic: 'blocks',
}

function Skeleton({ kind }: { kind: OutputKind }) {
  const shape = SHAPE[kind] ?? 'lines'
  const n = (count: number) => Array.from({ length: count }, (_, i) => <span key={i} />)
  return (
    <div className={`gen-skeleton gen-${shape}`} aria-hidden="true">
      {shape === 'lines' && (
        <>
          <span className="gen-head" />
          {n(4)}
        </>
      )}
      {shape === 'grid' && n(12)}
      {shape === 'nodes' && (
        <>
          <span className="gen-node a" />
          <span className="gen-node b" />
          <span className="gen-node c" />
          <span className="gen-link ab" />
          <span className="gen-link ac" />
        </>
      )}
      {shape === 'wave' && n(16)}
      {shape === 'card' && <span className="gen-flip" />}
      {shape === 'quiz' &&
        [0, 1].map((q) => (
          <span key={q} className="gen-q">
            <span className="gen-line" />
            {[0, 1, 2].map((i) => (
              <span key={i} className="gen-opt" />
            ))}
          </span>
        ))}
      {shape === 'bars' && n(5)}
      {shape === 'scale' && (
        <>
          <span className="gen-track" />
          <span className="gen-mark" />
        </>
      )}
      {shape === 'blocks' && n(6)}
    </div>
  )
}

/** While an output is made: a muted skeleton in its kind's shape with a
 *  slow shimmer (still under reduced motion), centred in the document
 *  view, and under it what is really happening: rag's phase when it sends
 *  one, the time since the output was created, and during a retry rag's
 *  error, which says which attempt follows. Nothing is made up. */
export function Generating({ kind, createdAt, phase, retry, outputId, fallback }: { kind: OutputKind; createdAt?: string | null; phase?: OutputPhase | null; retry?: string | null; outputId?: string; fallback: string }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const elapsed = createdAt ? elapsedLabel(createdAt, now) : null
  return (
    <div className="generating" role="status" aria-live="polite">
      <Skeleton kind={kind} />
      <p className="gen-status muted small">
        {[phase ? phaseLabel(phase) : fallback, elapsed].filter(Boolean).join(' · ')}
      </p>
      {/* a retry's error, unless the phase already says it */}
      {retry && phase?.step !== 'retry' && (
        <p className="gen-retry muted small">
          {retry} {outputId && <OutputId id={outputId} />}
        </p>
      )}
    </div>
  )
}
