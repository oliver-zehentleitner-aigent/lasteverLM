import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useMemo } from 'react'
import type { ReportContent } from '../../api/types'

/** Markdown from the model is untrusted: it is rendered, then sanitized
 *  before it touches the DOM. */
export function ReportView({ content }: { content: ReportContent }) {
  const html = useMemo(() => {
    const raw = marked.parse(content.markdown ?? '', { async: false, gfm: true }) as string
    return DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } })
  }, [content.markdown])
  return <div className="report" dangerouslySetInnerHTML={{ __html: html }} />
}
