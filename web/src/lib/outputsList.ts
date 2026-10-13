import type { Output, OutputKind } from '../api/types'
import { language } from '../i18n'
import { formatTime } from './format'
import { formFor, OUTPUT_FORMS } from './outputs'

/** How the Outputs list is ordered; newest first is the default because a
 *  kind is often generated again from the same sources. */
export const SORTS = ['newest', 'oldest', 'kind', 'language', 'status'] as const
export type Sort = (typeof SORTS)[number]

const STATUS_ORDER: Record<Output['status'], number> = { processing: 0, waiting: 1, failed: 2, ready: 3 }
const KIND_ORDER = new Map(OUTPUT_FORMS.map((f, i) => [f.kind, i]))
const newest = (a: Output, b: Output) => b.created_at.localeCompare(a.created_at)

/** A sorted copy; within equal keys the newest comes first. */
export function sortOutputs(outputs: readonly Output[], sort: Sort): Output[] {
  const list = [...outputs]
  switch (sort) {
    case 'oldest':
      return list.sort((a, b) => a.created_at.localeCompare(b.created_at))
    case 'kind':
      return list.sort((a, b) => (KIND_ORDER.get(a.kind) ?? 99) - (KIND_ORDER.get(b.kind) ?? 99) || newest(a, b))
    case 'language':
      // documents without a language ("as the sources") go last
      return list.sort((a, b) => {
        const x = a.options?.language
        const y = b.options?.language
        if (!x || !y) return (x ? -1 : y ? 1 : 0) || newest(a, b)
        return x.localeCompare(y) || newest(a, b)
      })
    case 'status':
      return list.sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || newest(a, b))
    default:
      return list.sort(newest)
  }
}

/** The kinds present, in the tile order, for the filter chips. */
export function kindsPresent(outputs: readonly Output[]): OutputKind[] {
  const present = new Set(outputs.map((o) => o.kind))
  return OUTPUT_FORMS.map((f) => f.kind).filter((k) => present.has(k))
}

/** Filter chips only pay off in a longer list. */
export const FILTER_FROM = 6

/** "14 min ago" for the last day, the absolute date and time after that. */
export function whenLabel(iso: string, now: Date = new Date()): string {
  const then = new Date(iso)
  const seconds = Math.round((then.getTime() - now.getTime()) / 1000)
  if (!Number.isFinite(seconds)) return iso
  if (-seconds >= 86_400) return formatTime(iso)
  const rtf = new Intl.RelativeTimeFormat(language(), { numeric: 'auto', style: 'short' })
  if (-seconds < 60) return rtf.format(0, 'minute')
  if (-seconds < 3600) return rtf.format(Math.round(seconds / 60), 'minute')
  return rtf.format(Math.round(seconds / 3600), 'hour')
}

/** "DE · Vivian": the language code and, for audio, the voice. */
export function optionsBrief(o: Output, voiceLabel: (id: string) => string): string {
  const parts: string[] = []
  if (o.options?.language) parts.push(o.options.language.toUpperCase())
  if (o.kind === 'audio' && o.options?.voice) parts.push(voiceLabel(o.options.voice))
  return parts.join(' · ')
}

/** The label a filter chip shows. */
export const kindLabel = (k: OutputKind) => formFor(k).label
