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

/** The word check's badge, only where it found no backing or could not
 *  measure, and only without a judge's verdict: the judge is the real
 *  check, its badge stands alone and carries the word check in its
 *  tooltip. A judge without a usable answer leaves the word check shown. */
export function supportBadge(s: Support | undefined, judged = false): Support | null {
  if (judged) return null
  return s === 'unsupported' || s === 'unverified' ? s : null
}

/** Whether a claim has a judge's verdict (a judge without a usable answer has none). */
export const hasVerdict = (c: Claim): boolean => !!c.judge?.verdict

/** "Have it judged · €0.02" after a claim the word check could not
 *  measure, as HTML for the renderers that take HTML; `ask` is the
 *  action's label with its price, absent where nothing can be judged. */
function askHtml(ask: string | undefined): string {
  return ask ? ` <button type="button" class="link small judge-ask" data-judge-ask="1" title="${t('judge.askTitle')}">${escapeAttr(ask)}</button>` : ''
}

function supportHtml(badge: Support, ask?: string): string {
  return `<span class="badge support-${badge}" title="${t('wordCheck.title')}">${t(`wordCheck.${badge}`)}</span>${badge === 'unverified' ? askHtml(ask) : ''}`
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
    const badge = supportBadge(u.support, hasVerdict(u))
    // the judge's badge carries the unit's index: the click looks its note up
    const insert = (badge ? ` ${SENTINEL(badge)}` : '') + (u.judge ? ` ⟦judge:${i}⟧` : '')
    out = out.slice(0, end) + insert + out.slice(end)
    from = end + insert.length
  }
  return out
}

/** The rendered report's markers as buttons (known passages only; others
 *  stay text, as in the chat), the sentinels as badges and the judge's
 *  badges. Only the text between tags is touched, in one pass: a marker
 *  inside an attribute (a judge's reason in a badge's title saying "Passage
 *  [1]") stays as it is, and what is inserted is never scanned again. Runs
 *  before sanitizing, so DOMPurify sees the buttons and spans too. */
export function decorateReport(html: string, known: ReadonlySet<number>, units: readonly Claim[] = [], ask?: string): string {
  return html
    .split(/(<[^>]*>)/)
    .map((part, i) => (i % 2 === 1 ? part : decorateText(part, known, units, ask)))
    .join('')
}

const TOKENS = /⟦judge:(\d+)⟧|⟦support:(supported|unsupported|unverified)⟧|\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g

function decorateText(text: string, known: ReadonlySet<number>, units: readonly Claim[], ask?: string): string {
  return text.replace(TOKENS, (whole, judge?: string, support?: string, list?: string) => {
    if (judge !== undefined) return judgeHtml(units[Number(judge)], Number(judge))
    if (support !== undefined) return supportHtml(support as Support, ask)
    const numbers = (list ?? '').split(',').map((s) => Number(s.trim()))
    if (!numbers.some((n) => known.has(n))) return whole
    return numbers.map((n) => (known.has(n) ? `<button type="button" class="cite" data-n="${n}">${n}</button>` : `[${n}]`)).join('')
  })
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
    const badge = supportBadge(u.support, hasVerdict(u))
    // a judged paragraph gets its judge badge even when the word check backed it
    if (badge || u.judge) out.push({ end: from, badge, unit: u })
  }
  return out
}

/** A claim's markers and badge as HTML, for a renderer that takes HTML (the
 *  mind map's labels); added before sanitizing, like the report's. */
export function claimHtml(c: Claim, known: ReadonlySet<number>, index?: number): string {
  const buttons = claimRefs(c, known).map((n) => `<button type="button" class="cite" data-n="${n}">${n}</button>`)
  const badge = supportBadge(c.support, hasVerdict(c) && index !== undefined)
  const span = badge ? supportHtml(badge) : ''
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
