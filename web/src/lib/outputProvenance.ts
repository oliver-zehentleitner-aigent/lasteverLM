import type { AnswerUnit, Check, Citation, Claim, Output, Passage, Provenance, Support } from '../api/types'
import { t, tn } from '../i18n'

/** What a generated document's claims rest on, shaped for the views: its
 *  passages as citations (the chat's provenance panel shows them), the
 *  check as one line, the log as a file. Pure, so it is tested. */

/** A passage as the chat's citation. On the share page the ids are left
 *  out; the panel then shows the stored quote and offers no source. */
export function passageCitation(p: Passage): Citation {
  return {
    n: p.n,
    source_id: p.source_id ?? '',
    source_name: p.source_name,
    source_kind: p.source_kind,
    chunk_id: p.chunk_id ?? '',
    page: p.page,
    quote: p.quote,
    similarity: p.similarity,
    chunk_index: p.chunk_index,
    chunk_count: p.chunk_count,
  }
}

/** The claim's passages that exist, in order, each once. */
export function claimRefs(c: Claim, known: ReadonlySet<number>): number[] {
  return [...new Set((c.refs ?? []).filter((n) => known.has(n)))]
}

/** A badge only where the check found no backing or could not measure it. */
export function supportBadge(s: Support | undefined): Exclude<Support, 'supported'> | null {
  return s === 'unsupported' || s === 'unverified' ? s : null
}

/** "7 of 9 claims supported", with the ones that could not be measured
 *  named after it; null without a check or without claims. */
export function checkSummary(check: Check | null | undefined): string | null {
  if (!check) return null
  const total = check.supported + check.unsupported + check.unverified
  if (total === 0) return null
  const line = tn('outProv.supported', total, { supported: check.supported })
  return check.unverified > 0 ? `${line} · ${tn('outProv.unverifiedN', check.unverified)}` : line
}

const SENTINEL = (s: string) => `⟦support:${s}⟧`
const SENTINELS = /⟦support:(unsupported|unverified)⟧/g
const MARKER = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g

/** The report's markdown with a sentinel after each paragraph the check
 *  did not back, found by its exact text in order (`units` are the
 *  non-heading paragraphs as written). A unit not found is left alone. */
export function markUnsupported(markdown: string, units: readonly ({ text: string } & Claim)[] | undefined): string {
  let out = markdown
  let from = 0
  for (const u of units ?? []) {
    const at = u.text ? out.indexOf(u.text, from) : -1
    if (at < 0) continue
    const end = at + u.text.length
    const badge = supportBadge(u.support)
    const insert = badge ? ` ${SENTINEL(badge)}` : ''
    out = out.slice(0, end) + insert + out.slice(end)
    from = end + insert.length
  }
  return out
}

/** The rendered report's markers as buttons (known passages only; others
 *  stay text, as in the chat) and the sentinels as badges. Runs before
 *  sanitizing, so DOMPurify sees the buttons and spans too. */
export function decorateReport(html: string, known: ReadonlySet<number>): string {
  return html
    .replace(MARKER, (whole, list: string) => {
      const numbers = list.split(',').map((s) => Number(s.trim()))
      if (!numbers.some((n) => known.has(n))) return whole
      return numbers.map((n) => (known.has(n) ? `<button type="button" class="cite" data-n="${n}">${n}</button>` : `[${n}]`)).join('')
    })
    .replace(SENTINELS, (_m, s: string) => `<span class="badge support-${s}" title="${t(`outProv.${s}Title` as 'outProv.unsupportedTitle')}">${t(`outProv.${s}` as 'outProv.unsupported')}</span>`)
}

/** How long the generation took, "12 s" or "2 min 5 s"; null when unknown. */
export function duration(p: Pick<Provenance, 'started_at' | 'finished_at'>): string | null {
  const ms = new Date(p.finished_at).getTime() - new Date(p.started_at).getTime()
  if (!Number.isFinite(ms) || ms < 0) return null
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}

/** The generation log as a downloadable file: the document's identity and
 *  its provenance as rag sent it. */
export function provenanceExport(o: Pick<Output, 'kind' | 'title' | 'created_at'> & { id?: string }, p: Provenance): string {
  return JSON.stringify({ output: { id: o.id, kind: o.kind, title: o.title, created_at: o.created_at }, provenance: p }, null, 2)
}

/** A file name for that export: the title in safe characters. */
export function exportName(title: string): string {
  const base = title.normalize('NFKD').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').toLowerCase().slice(0, 60)
  return `${base || 'document'}-provenance.json`
}

/** Where an answer's badges go: after each citing paragraph the check did
 *  not back, found by its exact text in order. Offsets into the answer. */
export function unitBadges(answer: string, units: readonly AnswerUnit[] | null | undefined): { end: number; badge: Exclude<Support, 'supported'> }[] {
  const out: { end: number; badge: Exclude<Support, 'supported'> }[] = []
  let from = 0
  for (const u of units ?? []) {
    const at = u.text ? answer.indexOf(u.text, from) : -1
    if (at < 0) continue
    from = at + u.text.length
    const badge = supportBadge(u.support)
    if (badge) out.push({ end: from, badge })
  }
  return out
}
