import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Citation, Claim, JudgeNote, Output, Provenance } from '../api/types'
import { formatTime } from '../lib/format'
import { claimRefs, duration, exportName, passageCitation, provenanceExport, supportBadge } from '../lib/outputProvenance'
import { optionsLabel } from '../lib/outputOptions'
import { isRemoved } from '../lib/citations'
import { ProvenancePanel } from './ProvenancePanel'
import { judgeBadge, verdictCounts } from '../lib/judge'
import { OutputId } from './OutputId'
import { CiteContext, useCite, type Cite } from '../hooks/useCite'
import { t } from '../i18n'


/** A claim's markers and, when the check did not back it, its badge;
 *  for units rendered as React (infographic facts, transcript turns). */
export function ClaimMarks({ claim, text }: { claim: Claim; text: string }) {
  const ctx = useCite()
  if (!ctx) return null
  const badge = supportBadge(claim.support, !!claim.judge)
  return (
    <>
      {claimRefs(claim, ctx.known).map((n) => (
        <button
          key={n}
          type="button"
          className={ctx.open === n ? 'cite open' : 'cite'}
          title={t('outProv.citeTitle', { n })}
          aria-pressed={ctx.open === n}
          onClick={() => ctx.cite(n, text)}
        >
          {n}
        </button>
      ))}
      {badge && (
        <span className={`badge support-${badge}`} title={t('wordCheck.title')}>
          {t(`wordCheck.${badge}`)}
        </span>
      )}
      <JudgeMark claim={claim} text={text} />
    </>
  )
}

/** The judge's verdict next to the word check's, amber-outlined where the
 *  two disagree; a click shows the reason and the decisive passage in the
 *  provenance panel (at the claim's first passage). */
export function JudgeMark({ claim, text }: { claim: Claim; text: string }) {
  const ctx = useCite()
  const b = judgeBadge(claim)
  if (!b || !claim.judge) return null
  const first = ctx ? claimRefs(claim, ctx.known)[0] : undefined
  const judge = claim.judge
  return (
    <button
      type="button"
      className={`badge judge judge-${b.verdict}${b.disagree ? ' disagree' : ''}`}
      title={b.title}
      disabled={first === undefined}
      onClick={() => first !== undefined && ctx?.cite(first, text, judge)}
    >
      {t('judge.section')}: {b.label}
    </button>
  )
}

interface Props {
  output: Pick<Output, 'kind' | 'title' | 'created_at'> & { id?: string }
  provenance: Provenance | null | undefined
  /** the notebook's sources, to tell a removed one; absent on the share page */
  presentSources?: ReadonlySet<string> | null
  /** "open in source"; absent on the share page */
  onOpenSource?: (c: Citation) => void
  children: ReactNode
}

/** A document with what it rests on: its renderer (given the markers
 *  through context), then the passages it cites, the one clicked last
 *  opened in the chat's provenance panel, then how it was made. Without
 *  provenance (older documents) only the renderer. */
export function OutputProvenance({ output, provenance, presentSources = null, onOpenSource, children }: Props) {
  const [open, setOpen] = useState<{ n: number; claim: string; judge?: JudgeNote } | null>(null)
  const panel = useRef<HTMLDivElement>(null)
  const passages = useMemo(() => provenance?.passages ?? [], [provenance])
  const known = useMemo(() => new Set(passages.map((p) => p.n)), [passages])
  const ctx = useMemo<Cite>(
    () => ({ known, open: open?.n ?? null, cite: (n, claim, judge) => setOpen((cur) => (cur?.n === n && cur.claim === claim ? null : { n, claim, judge })) }),
    [known, open],
  )

  // the panel is under the document: bring it into view, inside the viewer only
  useEffect(() => {
    if (open) panel.current?.scrollIntoView({ block: 'nearest' })
  }, [open])

  if (!provenance) return <>{children}</>
  const shown = open ? passages.find((p) => p.n === open.n) : undefined

  return (
    <CiteContext.Provider value={ctx}>
      {children}
      <section className="out-prov no-print">
        <div ref={panel}>
          {shown && (
            <ProvenancePanel
              citation={passageCitation(shown)}
              answer=""
              claim={open?.claim}
              judge={open?.judge}
              removed={shown.source_id ? isRemoved(shown.source_id, presentSources) : false}
              onOpenSource={onOpenSource}
            />
          )}
        </div>
        {passages.length > 0 && (
          <details className="out-sources">
            <summary>{t('outProv.sources', { n: passages.length })}</summary>
            <ol className="passages">
              {passages.map((p) => (
                <li key={p.n}>
                  <button type="button" className={open?.n === p.n ? 'cite open' : 'cite'} onClick={() => setOpen((cur) => (cur?.n === p.n ? null : { n: p.n, claim: '' }))}>
                    {p.n}
                  </button>{' '}
                  <span className="name" title={p.source_name}>
                    {p.source_name}
                  </span>
                  {p.page != null && <span className="muted small"> · {t('chat.page', { page: p.page })}</span>}
                </li>
              ))}
            </ol>
          </details>
        )}
        {(provenance.judge?.removed.length ?? 0) > 0 && <RemovedClaims removed={provenance.judge!.removed} />}
        <HowMade output={output} provenance={provenance} />
      </section>
    </CiteContext.Provider>
  )
}

/** The generation log, folded: what was asked, what retrieval found and
 *  used, the model, the usage, the time and the check; and the whole of
 *  it as a JSON file. */
function HowMade({ output, provenance: p }: { output: Props['output']; provenance: Provenance }) {
  const href = useMemo(() => URL.createObjectURL(new Blob([provenanceExport(output, p)], { type: 'application/json' })), [output, p])
  useEffect(() => () => URL.revokeObjectURL(href), [href])
  const took = duration(p)
  const usage = [
    p.usage.llm && t('outProv.usageLlm', { tin: p.usage.llm.tokens_in, tout: p.usage.llm.tokens_out }),
    p.usage.embedding && t('outProv.usageEmb', { tin: p.usage.embedding.tokens_in }),
    p.usage.tts && t('outProv.usageTts', { s: p.usage.tts.seconds }),
  ].filter(Boolean)
  return (
    <details className="how-made">
      <summary>{t('outProv.how')}</summary>
      <dl className="kv">
        {output.id && (
          <>
            <dt>{t('outputId.label')}</dt>
            <dd>
              <OutputId id={output.id} full />
            </dd>
          </>
        )}
        <dt>{t('outProv.model')}</dt>
        <dd>{p.model}</dd>
        <dt>{t('outProv.prompt')}</dt>
        <dd>{p.prompt_version}</dd>
        {optionsLabel(p.options, null) && (
          <>
            <dt>{t('outProv.options')}</dt>
            <dd>{optionsLabel(p.options, null)}</dd>
          </>
        )}
        {p.options.instructions && (
          <>
            <dt>{t('opt.authorInstructions')}</dt>
            <dd>{p.options.instructions}</dd>
          </>
        )}
        {p.focus_query && (
          <>
            <dt>{t('outProv.focus')}</dt>
            <dd>{p.focus_query}</dd>
          </>
        )}
        {usage.length > 0 && (
          <>
            <dt>{t('outProv.usage')}</dt>
            <dd>{usage.join(' · ')}</dd>
          </>
        )}
        <dt>{t('outProv.check')}</dt>
        <dd>
          {p.check.method}, {p.check.threshold} · ✓ {p.check.supported} · ✗ {p.check.unsupported} · ? {p.check.unverified}
        </dd>
        <dt>{t('outProv.when')}</dt>
        <dd>{took ? t('outProv.time', { start: formatTime(p.started_at), took }) : formatTime(p.started_at)}</dd>
      </dl>
      {p.calls && p.calls.length > 0 && (
        <div className="table-scroll">
          <table className="candidates calls">
            <caption className="muted small">{t('outProv.calls')}</caption>
            <thead>
              <tr>
                <th />
                <th>{t('outProv.model')}</th>
                <th>{t('outProv.prompt')}</th>
                <th>{t('outProv.when')}</th>
              </tr>
            </thead>
            <tbody>
              {p.calls.map((c, i) => (
                <tr key={i}>
                  <td>
                    {t(`outProv.call.${c.role}`)}
                    {c.state && <span className="muted small"> · {t('outProv.callState', { passages: c.state.passages, chars: c.state.chars })}</span>}
                  </td>
                  <td>{c.model}</td>
                  <td>{c.prompt_version}</td>
                  <td>{duration(c) ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {p.llm_verdict_text && (
        <p className="small">
          <span className="muted">{t('outProv.llmVerdict')}:</span> {p.llm_verdict_text}
        </p>
      )}
      {(p.judge || (p.judgements?.length ?? 0) > 0) && (
        <div className="judge-log">
          <h4>{t('judge.section')}</h4>
          {p.judge && (
            <>
              <p className="small">
                {t(`judge.level.${p.judge.level}`)} · {t('judge.model', { model: p.judge.model })}
              </p>
              <ul className="small">
                {p.judge.rounds.map((r) => (
                  <li key={r.round}>
                    {t('judge.roundLine', { round: r.round, judged: r.judged, counts: verdictCounts(r.verdicts), tin: r.usage.tokens_in, tout: r.usage.tokens_out })}
                    {r.revision && ` · ${t('judge.revisionLine', { revised: r.revision.revised, dropped: r.revision.dropped })}`}
                  </li>
                ))}
              </ul>
              {/* the list itself sits under the document, outside this fold, so it is never hidden */}
              {p.judge.removed.length > 0 && <p className="small">{t('judge.removed', { n: p.judge.removed.length })}</p>}
            </>
          )}
          {(p.judgements ?? []).map((j, i) => (
            <p key={i} className="small">
              {t('judge.later')} · {formatTime(j.at)} · {t(`judge.level.${j.level}`)} · {t('judge.model', { model: j.model })} · {verdictCounts(j.verdicts)}
            </p>
          ))}
        </div>
      )}
      <p className="muted small">{t('outProv.retrieval', { k: p.retrieval.k, floor: p.retrieval.floor })}</p>
      <div className="table-scroll">
        <table className="candidates">
          <thead>
            <tr>
              <th>{t('outProv.colSource')}</th>
              <th>{t('outProv.colPage')}</th>
              <th>{t('outProv.colSimilarity')}</th>
              <th>{t('outProv.colUsed')}</th>
            </tr>
          </thead>
          <tbody>
            {p.retrieval.candidates.map((c, i) => (
              <tr key={i} className={c.in_prompt ? undefined : 'muted'}>
                <td className="name">{c.source_name}</td>
                <td>{c.page ?? ''}</td>
                <td>{c.similarity.toFixed(2)}</td>
                <td>{c.in_prompt ? '✓' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <a className="small" href={href} download={exportName(output.title)}>
        {t('outProv.export')}
      </a>
    </details>
  )
}

/** The claims a judging took out, with the verdict and the reason; shown
 *  under the document and again in the log, never folded away. */
function RemovedClaims({ removed }: { removed: NonNullable<Provenance['judge']>['removed'] }) {
  return (
    <section className="judge-removed">
      <h4>{t('judge.removed', { n: removed.length })}</h4>
      <ul>
        {removed.map((r, i) => (
          <li key={i}>
            <q>{r.text}</q>{' '}
            <span className={`badge judge judge-${r.verdict === 'dropped in revision' ? 'dropped' : r.verdict}`}>{t(`judge.verdict.${r.verdict}`)}</span>{' '}
            <span className="muted small">
              {r.reason} · {t('judge.removedRound', { n: r.round })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
