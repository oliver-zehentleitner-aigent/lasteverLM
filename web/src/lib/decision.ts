import type { DecisionContent, DecisionType, OutputOptionsSpec } from '../api/types'
import { t } from '../i18n'

/** The decision kind's form values and its renderer's arithmetic. Pure,
 *  so it is tested. */

export const DECISION_TYPES: DecisionType[] = ['yes_no', 'choice', 'scale']

/** rag's limit for one option or level label. */
export const LABEL_MAX = 80

/** The limits the form checks, from rag's catalogue or, without one, the
 *  contract's numbers. */
export function decisionLimits(spec: OutputOptionsSpec | null) {
  return spec?.decision ?? { types: DECISION_TYPES, default_type: 'yes_no' as const, question_max_chars: 500, choices: { min: 2, max: 8 }, levels: { min: 3, max: 7 } }
}

/** Five ordered levels to start a scale with, lowest first. */
export function presetLevels(): string[] {
  return [1, 2, 3, 4, 5].map((i) => t(`decision.level${i}` as 'decision.level1'))
}

export interface DecisionValues {
  question: string
  decisionType: DecisionType
  choices: string[]
  levels: string[]
}

export function defaultDecision(spec: OutputOptionsSpec | null): DecisionValues {
  return { question: '', decisionType: decisionLimits(spec).default_type, choices: ['', ''], levels: presetLevels() }
}

const clean = (list: string[]) => list.map((s) => s.trim())

/** Why the form cannot be sent yet, as the hint under Create; null when it can. */
export function decisionProblem(v: DecisionValues, spec: OutputOptionsSpec | null): string | null {
  const lim = decisionLimits(spec)
  const q = v.question.trim()
  if (!q) return t('decision.needQuestion')
  if (q.length > lim.question_max_chars) return t('decision.tooLong', { n: lim.question_max_chars })
  const list = v.decisionType === 'choice' ? clean(v.choices) : v.decisionType === 'scale' ? clean(v.levels) : null
  if (!list) return null
  const { min, max } = v.decisionType === 'choice' ? lim.choices : lim.levels
  if (list.length < min || list.length > max) return t(v.decisionType === 'choice' ? 'decision.choiceCount' : 'decision.levelCount', { min, max })
  if (list.some((s) => !s)) return t('decision.emptyEntry')
  if (list.some((s) => s.length > LABEL_MAX)) return t('decision.labelTooLong', { n: LABEL_MAX })
  if (new Set(list.map((s) => s.toLowerCase())).size < list.length) return t('decision.duplicate')
  return null
}

/** The body's decision keys: the question, the type, and only the list the type uses. */
export function decisionOptions(v: DecisionValues, keys: readonly string[]) {
  const out: { question?: string; decision_type?: DecisionType; choices?: string[]; levels?: string[] } = {}
  if (keys.includes('question')) out.question = v.question.trim()
  if (keys.includes('decision_type')) out.decision_type = v.decisionType
  if (keys.includes('choices') && v.decisionType === 'choice') out.choices = clean(v.choices)
  if (keys.includes('levels') && v.decisionType === 'scale') out.levels = clean(v.levels)
  return out
}

/** A share 0–1 as a whole percent, clamped. */
export function percent(p: number): number {
  return Math.round(Math.min(1, Math.max(0, Number.isFinite(p) ? p : 0)) * 100)
}

/** Where on a segmented scale the weighted score sits, 0–100 % across
 *  the whole bar: score is a fractional index, and level i's segment has
 *  its middle at (i + 0.5) / n. */
export function scalePercent(score: number, levels: number): number {
  if (levels < 1 || !Number.isFinite(score)) return 50
  const clamped = Math.min(levels - 1, Math.max(0, score))
  return ((clamped + 0.5) / levels) * 100
}

/** The distribution in the order the options were given; an option the
 *  model left out counts 0, labels it added are appended. */
export function orderedDistribution(dist: Record<string, number>, order: readonly string[]): { label: string; p: number }[] {
  const seen = new Set(order)
  return [...order.map((label) => ({ label, p: dist[label] ?? 0 })), ...Object.keys(dist).filter((k) => !seen.has(k)).map((label) => ({ label, p: dist[label] }))]
}

/** Whether the decision model and the evidence point at different
 *  options (choice and scale), for the "model: B, evidence: A" line. */
export function modelVersusEvidence(c: DecisionContent): { model: string; evidence: string } | null {
  const a = c.model_answer
  if (undecided(c) || !a) return null
  const model = 'choice' in a ? a.choice : 'level' in a ? a.level : null
  if (!model || !c.llm_choice || c.llm_choice === model) return null
  return { model, evidence: c.llm_choice }
}

/** The sources do not decide the question: no number is shown, whatever
 *  the decision model said. rag sends `model_answer: null` for it; older
 *  outputs still carry numbers next to "undecided", which are ignored. */
export function undecided(c: Pick<DecisionContent, 'agreement' | 'model_answer'>): boolean {
  return c.agreement === 'undecided' || !c.model_answer
}

const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase()

/** Whether the question needs its own heading: not when the document's
 *  title already is the question (rag titles a decision with it). */
export function showQuestion(question: string, title: string | null | undefined): boolean {
  return !title || norm(title) !== norm(question)
}

/** A yes/no answer's two shares in whole percent, adding up to 100. */
export function yesNo(probabilityYes: number): { yes: number; no: number } {
  const yes = percent(probabilityYes)
  return { yes, no: 100 - yes }
}
