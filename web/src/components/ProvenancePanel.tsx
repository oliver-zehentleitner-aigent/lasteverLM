import { useEffect, useState } from 'react'
import { rag } from '../api/rag'
import type { Citation, JudgeNote } from '../api/types'
import { chunkPosition, claimFor, highlightPassage, similarityLabel, similarityPercent } from '../lib/provenance'
import { t } from '../i18n'
import { verdictKey } from '../lib/judge'
import { useSourceLink } from './SourceLinks'

interface Props {
  citation: Citation
  /** the answer the citation belongs to, to find the claim it backs */
  answer: string
  /** the statement it backs, when the caller knows it better than the answer's markers */
  claim?: string
  removed: boolean
  /** absent on the share page: no source to open there */
  onOpenSource?: (c: Citation) => void
  /** the judge's reading of the claim, when it was judged */
  judge?: JudgeNote
}

/** Where a cited statement comes from: the source, its page and chunk
 *  position, how similar the chunk was to the question, and the chunk
 *  text verbatim with the sentence that best matches the claim marked.
 *  Citations written before positions existed are completed from
 *  GET /chunks/{id} when the chunk is still there. */
export function ProvenancePanel({ citation, answer, claim, removed, onOpenSource, judge }: Props) {
  const sourceLink = useSourceLink()
  const external = citation.source_kind === 'generated' ? null : sourceLink(citation.source_id, citation.page)
  const [chunk, setChunk] = useState<{ text: string; index: number | null; count: number | null } | null>(null)
  const old = (citation.chunk_index === null || citation.chunk_index === undefined) && citation.chunk_id !== ''

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
  const passage = highlightPassage(text, claim ?? claimFor(answer, citation.n))

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
      {judge && (
        <div className={`judge-note judge-${verdictKey(judge)}`}>
          <strong>
            {t('judge.panelTitle')}: {t(`judge.verdict.${verdictKey(judge)}`)}
          </strong>{' '}
          <span className="muted small">
            ({t(`judge.level.${judge.level}`).toLowerCase()}, {judge.model}, {t('judge.removedRound', { n: judge.round })})
          </span>
          <p>{judge.reason}</p>
          {/* bulletproof: both judges, each with its own verdict and reason */}
          {judge.first && (
            <p className="small">
              <span className="muted">{t('judge.first', { model: judge.model })}:</span> {t(`judge.verdict.${judge.first.verdict ?? 'no_usable_answer'}`)} — {judge.first.reason}
            </p>
          )}
          {judge.second && (
            <p className="small">
              <span className="muted">{t('judge.second', { model: judge.second.model })}:</span> {t(`judge.verdict.${judge.second.verdict ?? 'no_usable_answer'}`)} — {judge.second.reason}
            </p>
          )}
          {judge.quote && (
            <p className="small">
              <span className="muted">{t('judge.quote')}:</span> <q>{judge.quote}</q>
            </p>
          )}
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
          onOpenSource && (
            <>
              <button type="button" className="link" onClick={() => onOpenSource(citation)}>
                {citation.source_kind === 'generated' ? t('prov.openDoc') : t('prov.open')}
              </button>
              {external && (
                <a className="icon-link" href={external} target="_blank" rel="noopener noreferrer" title={t('srcView.newTab')} aria-label={t('srcView.newTab')}>
                  ↗
                </a>
              )}
            </>
          )
        )}
        {passage.match && <span className="muted small">{t('prov.marked')}</span>}
      </footer>
    </aside>
  )
}
