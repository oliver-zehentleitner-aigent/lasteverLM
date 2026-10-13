import type { Preferences } from '../api/types'
import { t } from '../i18n'

/** How ingest reads a PDF. Only PDFs take a mode; other files ignore it. */
export type CaptureMode = 'auto' | 'text' | 'vision'

const mode = (m: CaptureMode) => ({
  mode: m,
  get label() {
    return t(`capture.${m}`)
  },
  get explain() {
    return t(`capture.${m}.note`)
  },
})

export const CAPTURE_MODES: { mode: CaptureMode; readonly label: string; readonly explain: string }[] = [mode('auto'), mode('text'), mode('vision')]

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
