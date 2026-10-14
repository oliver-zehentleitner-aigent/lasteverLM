import type { OutputKind, Source, SourceKind } from '../api/types'
import { t } from '../i18n'

/** The output forms offered as tiles, in display order. Labels and
 *  descriptions are getters, so they follow the current language. `available: false`
 *  shows the tile disabled with "Soon." (see `tileNote`), so the shape of
 *  the panel is complete before every generator exists and enabling one is
 *  a one-line change. `printable` enables the print
 *  action; mind maps, infographics and audio are not printed. */
export interface OutputForm {
  kind: OutputKind
  label: string
  description: string
  available: boolean
  printable: boolean
}

export const OUTPUT_FORMS: OutputForm[] = [
  { kind: 'report', get label() { return t('kind.report') }, get description() { return t('kind.report.note') }, available: true, printable: true },
  { kind: 'quiz', get label() { return t('kind.quiz') }, get description() { return t('kind.quiz.note') }, available: true, printable: false },
  { kind: 'table', get label() { return t('kind.table') }, get description() { return t('kind.table.note') }, available: true, printable: true },
  { kind: 'mindmap', get label() { return t('kind.mindmap') }, get description() { return t('kind.mindmap.note') }, available: true, printable: false },
  { kind: 'infographic', get label() { return t('kind.infographic') }, get description() { return t('kind.infographic.note') }, available: true, printable: false },
  { kind: 'audio', get label() { return t('kind.audio') }, get description() { return t('kind.audio.note') }, available: true, printable: false },
  { kind: 'decision', get label() { return t('kind.decision') }, get description() { return t('kind.decision.note') }, available: true, printable: true },
]

export function formFor(kind: OutputKind): OutputForm {
  return (
    OUTPUT_FORMS.find((f) => f.kind === kind) ?? { kind, label: kind, description: '', available: false, printable: false }
  )
}

/** Source types offered in the wizard's first step. */
export interface SourceForm {
  kind: Exclude<SourceKind, 'generated'>
  label: string
  description: string
  available: boolean
  /** which input the second step shows */
  input: 'files' | 'url' | 'paste'
  accept?: string
}

export const SOURCE_FORMS: SourceForm[] = [
  { kind: 'pdf', get label() { return t('source.pdf') }, get description() { return t('source.pdf.note') }, available: true, input: 'files', accept: '.pdf,application/pdf' },
  { kind: 'text', get label() { return t('source.text') }, get description() { return t('source.text.note') }, available: true, input: 'files', accept: '.txt,.md,text/plain,text/markdown' },
  { kind: 'url', get label() { return t('source.url') }, get description() { return t('source.url.note') }, available: true, input: 'url' },
  {
    kind: 'image',
    get label() {
      return t('source.image')
    },
    get description() {
      return t('source.image.note')
    },
    available: true,
    input: 'files',
    accept: '.png,.jpg,.jpeg,.webp,.gif,image/png,image/jpeg,image/webp,image/gif',
  },
  {
    kind: 'audio',
    get label() {
      return t('source.audio')
    },
    get description() {
      return t('source.audio.note')
    },
    available: true,
    input: 'files',
    accept: '.mp3,.wav,.m4a,.aac,.ogg,.oga,.opus,.flac,.webm,.mp4,audio/*,video/mp4,video/webm',
  },
]

/** A source kind as the interface names it; `generated` has no tile. */
export function sourceKindLabel(kind: SourceKind): string {
  return SOURCE_FORMS.find((f) => f.kind === kind)?.label ?? (kind === 'generated' ? t('source.generated') : kind)
}

/** The line under a tile's label: its description, or "Soon." while the
 *  form is not available yet. */
export function tileNote(f: { description: string; available: boolean }): string {
  return f.available ? f.description : t('tile.soon')
}

/** The sources a user added. A document made in this notebook is a
 *  source of kind `generated` too, so the chat can cite it, but it is
 *  listed under Outputs; one added from the library (made elsewhere) is
 *  listed here like an upload. `ownGenerated` holds the source ids of this
 *  notebook's documents; null while they are loading, then every
 *  generated source is left out rather than shown twice for a moment. */
export function uploadedSources(sources: readonly Source[], ownGenerated: ReadonlySet<string> | null = null): Source[] {
  return sources.filter((s) => s.kind !== 'generated' || (ownGenerated !== null && !ownGenerated.has(s.id)))
}

/** Why the Create button is disabled, as the hint under it, or null when
 *  a job can start: a format must be picked and a source must be ready. */
export function createBlocker(selected: OutputKind | null, hasReadySource: boolean, noneSelected = false): string | null {
  if (noneSelected) return t('create.needSelected')
  if (!hasReadySource) return t('create.needSource')
  if (!selected) return t('create.needFormat')
  return null
}
