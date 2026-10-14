import DOMPurify from 'dompurify'

/** The one sanitizer for HTML that came from a model: the report's
 *  rendered Markdown and the mind map's labels go through it before they
 *  reach the DOM. */
export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } })
}
