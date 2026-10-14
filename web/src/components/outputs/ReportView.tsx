import { marked } from 'marked'
import { useMemo, type MouseEvent } from 'react'
import type { ReportContent } from '../../api/types'
import { decorateReport, markUnsupported } from '../../lib/outputProvenance'
import { useCite } from '../../hooks/useCite'
import { sanitizeHtml } from '../../lib/sanitize'

/** Markdown from the model is untrusted: it is rendered, then sanitized
 *  before it touches the DOM. With provenance its [n] markers become
 *  buttons that show the passage, and a paragraph the check did not back
 *  gets a badge; both are added before sanitizing. */
export function ReportView({ content }: { content: ReportContent }) {
  const cite = useCite()
  const known = cite?.known
  const html = useMemo(() => {
    const markdown = known ? markUnsupported(content.markdown ?? '', content.units) : (content.markdown ?? '')
    const raw = marked.parse(markdown, { async: false, gfm: true }) as string
    return sanitizeHtml(known ? decorateReport(raw, known) : raw)
  }, [content.markdown, content.units, known])

  function onClick(e: MouseEvent<HTMLDivElement>) {
    const button = (e.target as HTMLElement).closest<HTMLButtonElement>('button.cite[data-n]')
    if (!button || !cite) return
    // the claim is the block the marker sits in, for the panel's highlight
    const block = button.closest('p, li, td, blockquote')
    cite.cite(Number(button.dataset.n), block?.textContent ?? '')
  }

  return <div className="report" onClick={onClick} dangerouslySetInnerHTML={{ __html: html }} />
}
