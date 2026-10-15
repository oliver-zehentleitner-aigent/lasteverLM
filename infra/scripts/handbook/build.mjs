// Renders the handbook: the repository's docs in a fixed order, as one PDF with
// a title page and a table of contents. Runs inside the Playwright image
// (scripts/handbook.sh); reads the checkout from /repo, writes OUT.
import { readFileSync } from 'node:fs'
import { marked } from 'marked'
import { chromium } from 'playwright'

const DOCS = [
  'docs/project.md',
  'docs/architecture.md',
  'docs/rag-pipeline.md',
  'docs/ui.md',
  'rag/docs/judge-eval.md',
  'infra/docs/operations.md',
  'account/docs/operations.md',
  'ingest/docs/README.md',
  'core/docs/README.md',
  'docs/repository-standard.md',
]
const { VERSION, DATE, OUT } = process.env
if (!VERSION || !DATE || !OUT) {
  console.error('VERSION, DATE and OUT are required')
  process.exit(2)
}

const escape = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
// The heading's HTML without its tags, stripped until nothing changes, so a
// tag that a removal puts together is removed as well.
const stripTags = (s) => {
  for (let before = null; before !== s; ) {
    before = s
    s = s.replace(/<[^>]+>/g, '')
  }
  return s
}
const slug = (s) => stripTags(s.toLowerCase()).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

// Every heading gets an id unique across the book (chapter number first), the
// chapter's own title (its first heading) becomes the chapter heading, and the
// chapter title and its second-level headings go into the table of contents.
const toc = []
const chapters = DOCS.map((path, i) => {
  const n = i + 1
  let title = null
  const seen = new Map()
  const renderer = new marked.Renderer()
  renderer.heading = function ({ tokens, depth }) {
    const text = this.parser.parseInline(tokens)
    const base = `c${n}-${slug(text) || 'section'}`
    const count = seen.get(base) ?? 0
    seen.set(base, count + 1)
    const id = count ? `${base}-${count}` : base
    if (title === null) {
      title = text
      toc.push({ level: 1, id, text: `${n}. ${text}` })
      return `<h1 class="chapter" id="${id}">${n}. ${text}</h1><p class="path">${escape(path)}</p>\n`
    }
    if (depth === 2) toc.push({ level: 2, id, text })
    return `<h${Math.min(depth + 1, 6)} id="${id}">${text}</h${Math.min(depth + 1, 6)}>\n`
  }
  const html = marked.parse(readFileSync('/repo/' + path, 'utf8'), { renderer, gfm: true })
  return `<section class="doc">${html}</section>`
})

const tocHtml = toc
  .map((e) => `<li class="l${e.level}"><a href="#${e.id}">${e.text}</a></li>`)
  .join('\n')

const css = `
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 9.5pt; line-height: 1.45; color: #111; }
.title { height: 240mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always; }
.title h1 { font-size: 26pt; margin: 0 0 8mm; border: 0; }
.title p { font-size: 12pt; margin: 2mm 0; color: #333; }
nav.toc { page-break-after: always; }
nav.toc h1 { font-size: 16pt; }
nav.toc ul { list-style: none; padding: 0; margin: 0; }
nav.toc li.l1 { font-weight: bold; margin-top: 3mm; }
nav.toc li.l2 { margin-left: 6mm; font-size: 9pt; }
nav.toc a { color: #111; text-decoration: none; }
section.doc { page-break-before: always; }
h1.chapter { font-size: 18pt; border-bottom: 1px solid #999; padding-bottom: 2mm; margin-bottom: 1mm; }
p.path { font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; color: #555; margin-top: 0; }
h2 { font-size: 14pt; margin-top: 7mm; } h3 { font-size: 12pt; } h4, h5, h6 { font-size: 10.5pt; }
h2, h3, h4, h5, h6 { page-break-after: avoid; break-after: avoid; }
code { font-family: "DejaVu Sans Mono", "Liberation Mono", monospace; font-size: 8.5pt; background: #f2f2f2; padding: 0 2px; overflow-wrap: anywhere; }
pre { background: #f5f5f5; border: 1px solid #ddd; padding: 2.5mm; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 8pt; line-height: 1.35; }
pre code { background: none; padding: 0; font-size: 8pt; }
table { border-collapse: collapse; width: 100%; font-size: 8pt; margin: 3mm 0; table-layout: auto; }
th, td { border: 1px solid #bbb; padding: 1.2mm 1.5mm; vertical-align: top; overflow-wrap: anywhere; word-break: normal; }
th { background: #eee; text-align: left; }
tr { page-break-inside: avoid; break-inside: avoid; }
a { color: #0645ad; overflow-wrap: anywhere; }
blockquote { border-left: 3px solid #ccc; margin-left: 0; padding-left: 4mm; color: #333; }
img { max-width: 100%; }
`

const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>lasteverLM — complete technical description</title><style>${css}</style></head><body>
<div class="title"><h1>lasteverLM — complete technical description</h1><p>Version ${escape(VERSION)}</p><p>${escape(DATE)}</p><p>Built from the repository's documentation, in this order: ${DOCS.map(escape).join(', ')}.</p></div>
<nav class="toc"><h1>Contents</h1><ul>${tocHtml}</ul></nav>
${chapters.join('\n')}
</body></html>`

const browser = await chromium.launch()
const page = await browser.newPage()
await page.setContent(html, { waitUntil: 'load' })
await page.pdf({
  path: OUT,
  format: 'A4',
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: '<span></span>',
  footerTemplate: `<div style="font-size:8px;width:100%;padding:0 16mm;color:#555;display:flex;justify-content:space-between"><span>lasteverLM ${escape(VERSION)}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  margin: { top: '18mm', bottom: '18mm', left: '16mm', right: '16mm' },
  outline: true,
  tagged: true,
})
await browser.close()
console.log(`wrote ${OUT}: ${DOCS.length} documents, ${toc.filter((e) => e.level === 2).length} sections in the contents`)
