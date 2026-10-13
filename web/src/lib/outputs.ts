import type { OutputKind, SourceKind } from '../api/types'

/** The output forms offered as tiles, in display order. `available: false`
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
  { kind: 'report', label: 'Report', description: 'A structured write-up of the sources.', available: true, printable: true },
  { kind: 'quiz', label: 'Quiz', description: 'Questions with answers and explanations.', available: true, printable: false },
  { kind: 'table', label: 'Data table', description: 'Facts from the sources as rows and columns.', available: true, printable: true },
  { kind: 'mindmap', label: 'Mindmap', description: 'Topics and sub-topics as a tree.', available: true, printable: false },
  { kind: 'infographic', label: 'Infographic', description: 'Headline, key facts and short sections.', available: true, printable: false },
  { kind: 'audio', label: 'Audio', description: 'A spoken overview of the sources.', available: false, printable: false },
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
  { kind: 'pdf', label: 'PDF', description: 'Drop or pick one or more PDF files.', available: true, input: 'files', accept: '.pdf,application/pdf' },
  { kind: 'text', label: 'Text', description: 'Plain text or Markdown files, or paste text.', available: true, input: 'files', accept: '.txt,.md,text/plain,text/markdown' },
  { kind: 'url', label: 'Web page', description: 'The address of a web page, or of a PDF or text file.', available: true, input: 'url' },
  {
    kind: 'image',
    label: 'Image',
    description: 'PNG, JPEG, WebP or GIF; the text in it is transcribed and the picture described.',
    available: true,
    input: 'files',
    accept: '.png,.jpg,.jpeg,.webp,.gif,image/png,image/jpeg,image/webp,image/gif',
  },
]

/** The line under a tile's label: its description, or "Soon." while the
 *  form is not available yet. */
export function tileNote(f: { description: string; available: boolean }): string {
  return f.available ? f.description : 'Soon.'
}
