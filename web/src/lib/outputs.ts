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
    accept: '.mp3,.wav,audio/mpeg,audio/wav,audio/x-wav',
  },
]

/** The line under a tile's label: its description, or "Soon." while the
 *  form is not available yet. */
export function tileNote(f: { description: string; available: boolean }): string {
  return f.available ? f.description : t('tile.soon')
}

/** The sources a user added. A generated document is a source of kind
 *  `generated` too, so the chat can cite it, but it is listed under
 *  Outputs, not among the uploads. */
export function uploadedSources(sources: readonly Source[]): Source[] {
  return sources.filter((s) => s.kind !== 'generated')
}

/** Why the Create button is disabled, as the hint under it, or null when
 *  a job can start: a format must be picked and a source must be ready. */
export function createBlocker(selected: OutputKind | null, hasReadySource: boolean, noneSelected = false): string | null {
  if (noneSelected) return t('create.needSelected')
  if (!hasReadySource) return t('create.needSource')
  if (!selected) return t('create.needFormat')
  return null
}
