import type { AnswerUnit, Check, Citation, Claim, Output, Passage, Provenance, Support } from '../api/types'
import { t, tn } from '../i18n'
import { judgeBadge } from './judge'

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
export function supportBadge(s: Support | undefined, judged = false): Support | null {
  // "supported" only next to a judge's badge, so the two checks read as a pair;
  // without a judge a backed claim stays unmarked, as before
  if (s === 'supported') return judged ? s : null
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
const SENTINELS = /⟦support:(supported|unsupported|unverified)⟧/g
const MARKER = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g

/** The report's markdown with a sentinel after each paragraph the check
 *  did not back, found by its exact text in order (`units` are the
 *  non-heading paragraphs as written). A unit not found is left alone. */
export function markUnsupported(markdown: string, units: readonly ({ text: string } & Claim)[] | undefined): string {
  let out = markdown
  let from = 0
  for (const [i, u] of (units ?? []).entries()) {
    const at = u.text ? out.indexOf(u.text, from) : -1
    if (at < 0) continue
    const end = at + u.text.length
    const badge = supportBadge(u.support, !!u.judge)
    // the judge's badge carries the unit's index: the click looks its note up
    const insert = (badge ? ` ${SENTINEL(badge)}` : '') + (u.judge ? ` ⟦judge:${i}⟧` : '')
    out = out.slice(0, end) + insert + out.slice(end)
    from = end + insert.length
  }
  return out
}

/** The rendered report's markers as buttons (known passages only; others
 *  stay text, as in the chat) and the sentinels as badges. Runs before
 *  sanitizing, so DOMPurify sees the buttons and spans too. */
export function decorateReport(html: string, known: ReadonlySet<number>, units: readonly Claim[] = []): string {
  return html
    .replace(/⟦judge:(\d+)⟧/g, (_m, i: string) => judgeHtml(units[Number(i)], Number(i)))
    .replace(MARKER, (whole, list: string) => {
      const numbers = list.split(',').map((s) => Number(s.trim()))
      if (!numbers.some((n) => known.has(n))) return whole
      return numbers.map((n) => (known.has(n) ? `<button type="button" class="cite" data-n="${n}">${n}</button>` : `[${n}]`)).join('')
    })
    .replace(SENTINELS, (_m, s: string) => `<span class="badge support-${s}" title="${t('wordCheck.title')}">${t(`wordCheck.${s}` as 'wordCheck.unsupported')}</span>`)
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
export function unitBadges(answer: string, units: readonly AnswerUnit[] | null | undefined): { end: number; badge: Support | null; unit: AnswerUnit }[] {
  const out: { end: number; badge: Support | null; unit: AnswerUnit }[] = []
  let from = 0
  for (const u of units ?? []) {
    const at = u.text ? answer.indexOf(u.text, from) : -1
    if (at < 0) continue
    from = at + u.text.length
    const badge = supportBadge(u.support, !!u.judge)
    // a judged paragraph gets its judge badge even when the word check backed it
    if (badge || u.judge) out.push({ end: from, badge, unit: u })
  }
  return out
}

/** A claim's markers and badge as HTML, for a renderer that takes HTML (the
 *  mind map's labels); added before sanitizing, like the report's. */
export function claimHtml(c: Claim, known: ReadonlySet<number>, index?: number): string {
  const buttons = claimRefs(c, known).map((n) => `<button type="button" class="cite" data-n="${n}">${n}</button>`)
  const badge = supportBadge(c.support, !!c.judge && index !== undefined)
  const span = badge ? `<span class="badge support-${badge}" title="${t('wordCheck.title')}">${t(`wordCheck.${badge}`)}</span>` : ''
  const judge = c.judge && index !== undefined ? judgeHtml(c, index) : ''
  return buttons.length || span || judge ? ` ${buttons.join('')}${span}${judge}` : ''
}

const escapeAttr = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

/** A unit's judge badge as HTML, `data-u` its index among the renderer's
 *  units; the reason (model text) is escaped, and sanitized after. */
function judgeHtml(c: Claim | undefined, index: number): string {
  const b = c ? judgeBadge(c) : null
  if (!b) return ''
  return `<button type="button" class="badge judge judge-${b.verdict}${b.disagree ? ' disagree' : ''}" data-u="${index}" title="${escapeAttr(b.title)}">${escapeAttr(`${t('judge.section')}: ${b.label}`)}</button>`
}
