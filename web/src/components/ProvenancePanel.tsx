import { useEffect, useState } from 'react'
import { rag } from '../api/rag'
import type { Citation } from '../api/types'
import { chunkPosition, claimFor, highlightPassage, similarityLabel, similarityPercent } from '../lib/provenance'
import { t } from '../i18n'

interface Props {
  citation: Citation
  /** the answer the citation belongs to, to find the claim it backs */
  answer: string
  removed: boolean
  onOpenSource: (c: Citation) => void
}

/** Where a cited statement comes from: the source, its page and chunk
 *  position, how similar the chunk was to the question, and the chunk
 *  text verbatim with the sentence that best matches the claim marked.
 *  Citations written before positions existed are completed from
 *  GET /chunks/{id} when the chunk is still there. */
export function ProvenancePanel({ citation, answer, removed, onOpenSource }: Props) {
  const [chunk, setChunk] = useState<{ text: string; index: number | null; count: number | null } | null>(null)
  const old = citation.chunk_index === null || citation.chunk_index === undefined

  useEffect(() => {
    if (!old) return
    let live = true
    rag.getChunk(citation.chunk_id).then(
      (c) => live && setChunk({ text: c.text, index: c.chunk_index, count: c.chunk_count }),
      () => {
        // gone or not visible: the stored quote is all there is
      },
    )
    return () => {
      live = false
    }
  }, [old, citation.chunk_id])

  const text = chunk?.text ?? citation.quote
  const position = chunkPosition(chunk?.index ?? citation.chunk_index, chunk?.count ?? citation.chunk_count)
  const sim = similarityLabel(citation.similarity)
  const passage = highlightPassage(text, claimFor(answer, citation.n))

  return (
    <aside className="provenance" aria-label={t('prov.label', { n: citation.n })}>
      <header>
        <strong className="name" title={citation.source_name}>
          [{citation.n}] {citation.source_name}
        </strong>
        <span className="badge">{citation.source_kind}</span>
        {citation.page != null && <span className="muted small">{t('chat.page', { page: citation.page })}</span>}
        {position && <span className="muted small">{position}</span>}
      </header>
      {sim !== null && citation.similarity != null && (
        <div className="similarity" title={t('prov.similarityTitle')}>
          <span className="muted small">{t('prov.similarity')}</span>
          <span className="bar" aria-hidden="true">
            <span style={{ width: `${similarityPercent(citation.similarity)}%` }} />
          </span>
          <span className="value">{sim}</span>
        </div>
      )}
      <blockquote className="chunk">
        {passage.before}
        {passage.match && <mark>{passage.match}</mark>}
        {passage.after}
      </blockquote>
      <footer>
        {removed ? (
          <span className="muted small">{t('prov.gone')}</span>
        ) : (
          <button type="button" className="link" onClick={() => onOpenSource(citation)}>
            {citation.source_kind === 'generated' ? t('prov.openDoc') : t('prov.open')}
          </button>
        )}
        {passage.match && <span className="muted small">{t('prov.marked')}</span>}
      </footer>
    </aside>
  )
}
