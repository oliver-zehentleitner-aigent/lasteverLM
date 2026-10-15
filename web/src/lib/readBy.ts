import type { ReadBy, SourceKind } from '../api/types'
import { t } from '../i18n'

/** The line saying a model, not a person or a text layer, produced what
 *  was read: "Described by <model>, not a verbatim transcript" for an
 *  image, "Page read by <model>" for a PDF page the vision model read
 *  (`vision`: that chunk's page), "Transcribed by <model>" for audio; null
 *  where nothing was recorded or the text came as written. Pure, so it is
 *  tested. */
export function readByLine(kind: SourceKind, readBy: ReadBy | null | undefined, vision?: boolean): string | null {
  if (!readBy) return null
  if (kind === 'image' && readBy.vision) return t('readBy.image', { model: readBy.vision })
  if (kind === 'pdf' && readBy.vision && vision) return t('readBy.page', { model: readBy.vision })
  if (kind === 'audio' && readBy.stt) return t('readBy.audio', { model: readBy.stt })
  return null
}
