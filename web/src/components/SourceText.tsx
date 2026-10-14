import { marked } from 'marked'
import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { ingest } from '../api/ingest'
import type { Source } from '../api/types'
import { t } from '../i18n'
import { sanitizeHtml } from '../lib/sanitize'

/** The Original of a text or Markdown source, inline: the stored file as
 *  ingest gives it (`/sources/{id}/text`; over 2 MiB a 413, shown with a
 *  link to the file), also before it is
 *  read. Plain text in monospace, Markdown rendered and sanitized like a
 *  report. */
export function SourceText({ source }: { source: Source }) {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tooLarge, setTooLarge] = useState(false)
  const markdown = /\.(md|markdown)$/i.test(source.name)

  useEffect(() => {
    let live = true
    ingest.sourceText(source.id).then(
      (s) => live && setText(s),
      (e: unknown) => {
        if (!live) return
        setTooLarge(e instanceof ApiError && e.status === 413)
        setError(e instanceof Error ? e.message : String(e))
      },
    )
    return () => {
      live = false
    }
  }, [source.id])

  const html = useMemo(() => (text !== null && markdown ? sanitizeHtml(marked.parse(text, { async: false, gfm: true }) as string) : null), [text, markdown])

  if (error)
    return (
      <p className="error">
        {error}
        {/* too large to show (413): the file itself, in a new tab */}
        {tooLarge && source.preview_url && (
          <>
            {' '}
            <a href={source.preview_url} target="_blank" rel="noopener noreferrer">
              {t('srcView.openFile')}
            </a>
          </>
        )}
      </p>
    )
  if (text === null) return <p className="muted">{t('common.loading')}</p>
  if (html !== null) return <div className="report source-markdown" dangerouslySetInnerHTML={{ __html: html }} />
  return <pre className="source-plain">{text}</pre>
}
