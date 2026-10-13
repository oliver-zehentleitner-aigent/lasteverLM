import type { Preferences } from '../api/types'

/** How ingest reads a PDF. Only PDFs take a mode; other files ignore it. */
export type CaptureMode = 'auto' | 'text' | 'vision'

export const CAPTURE_MODES: { mode: CaptureMode; label: string; explain: string }[] = [
  { mode: 'auto', label: 'Auto', explain: 'Text layer where present, the vision model for scanned pages.' },
  { mode: 'text', label: 'Text', explain: 'Text layer only; scanned pages fail.' },
  { mode: 'vision', label: 'Vision', explain: 'Every page read by the vision model, one model call per page.' },
]

/** The user's default: the preference when set, else auto. */
export function preferredCapture(prefs: Preferences | undefined): CaptureMode {
  return prefs?.pdf_capture ?? 'auto'
}

export function isPdf(file: Pick<File, 'name' | 'type'>): boolean {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}

/** "PDF · vision" for a source or library entry with a mode, else the kind. */
export function kindWithCapture(kindLabel: string, capture: CaptureMode | null | undefined): string {
  return capture ? `${kindLabel} · ${capture}` : kindLabel
}
