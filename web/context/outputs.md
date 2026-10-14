# Generated documents

## Model output is untrusted content: sanitized Markdown, React for the rest

**Id:** 1fd15f00-415a-46aa-89ec-d8f4d094c94c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-12
**Revisit when:** a renderer needs raw HTML from the model, or the sanitizer's profile has to be widened

Reports arrive as Markdown written by a language model from user-uploaded
sources. They are rendered with `marked` and passed through DOMPurify
before `dangerouslySetInnerHTML`. The mind map's labels go through
markmap, which renders each node as HTML, so every node is passed
through DOMPurify too (this was missed at first and fixed on
2026-10-14). The other kinds (quiz, table, infographic) are rendered
through React, which escapes text. The shared page `/s/<token>` uses the
same renderers.

**Reason:** the content is only as trustworthy as the sources it was
generated from, and the share page shows it to people who never logged
in. A stored-XSS path from an uploaded PDF through a report to a reader
of a shared link is exactly what sanitizing closes.

**Rejected alternative:** a Markdown-to-React renderer that never
produces an HTML string. Rejected as a larger dependency for the same
result; `marked` plus DOMPurify is small and well understood.

With provenance (2026-10-14) a report's `[n]` markers become buttons and
a paragraph the check did not back gets a badge. Both are added to the
rendered HTML before it is sanitized, so DOMPurify sees them like the
model's own markup; the click is handled by one listener on the
container, so the HTML needs no event attributes.

**Rejected alternative:** inserting the buttons and badges after
sanitizing. Rejected because string edits on sanitized HTML are trusted
blindly: a marker that happened to sit inside an attribute would be
turned into markup no sanitizer checked.

## markmap is loaded on demand

**Id:** c052fbee-b171-4ac1-9149-ed6afd66a5d4
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-12; build output of the same day

The mind map renderer imports `markmap-lib` and `markmap-view` with a
dynamic `import()`, so the chunk (it carries d3) is fetched only when a
mind map is opened. The chunk is larger than Vite's default warning
limit; the limit is raised in `vite.config.ts` with a comment saying why.

**Reason:** the main bundle is what every visitor downloads, the mind map
is one of six kinds. The family spec names markmap, so replacing it was
not on the table; a lighter tree renderer would mean a second
visualization to maintain.

**Rejected alternative:** importing markmap statically. Rejected because
it would more than double the initial download for a feature most page
loads never use.

## A citation into a generated document is matched to its tab by title

**Id:** cc84ab20-2a74-4b74-8eb8-81114446b0d2
**Type:** workaround
**Status:** superseded
**Superseded by:** 76c108f7-ef87-4bca-b779-83c9b0a56e4d
**Evidence:** confirmed
**Source:** implementation decision, 2026-10-12, against API contract v1.1

Before the contract gave an output a reference to its generated source,
the frontend found the tab for a citation with `source_kind: generated`
by comparing the source name with the output title. Replaced the same
day once `Output.source_id` was added to the contract; see below.

## A citation into a generated document opens its tab through Output.source_id

**Id:** 76c108f7-ef87-4bca-b779-83c9b0a56e4d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family contract change, 2026-10-12, on this repository's proposal

When a document is ready, rag indexes its text as a source of kind
`generated` and records that source's id on the output
(`Output.source_id`). A citation whose `source_kind` is `generated`
therefore names the output directly: the frontend selects the output
whose `source_id` equals the citation's `source_id` and opens its tab.

**Reason:** the id is exact where a title match was fragile (repeated or
edited titles), and it is one field on a row rag already owns.

**Rejected alternative:** an `output_id` on the citation. Rejected by
the family lead as a change to a shape three services read, for the same
information the output row can carry.

## "Open document" finds the cited passage by shared words, not by an offset

**Id:** 5d273729-62b8-4f7a-8b4b-ee44f27a6a0c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer request relayed by the family lead, 2026-10-13 (open the generated document, scroll to and flash the matching text, in a mind map the node matching the chunk's first line); how the passage is found was this directory's call
**Revisit when:** a citation into a generated document carries a position in its Markdown, or a browser run shows the wrong block flashing

For a citation into a generated document, "open document" opens its
tab and then looks for the passage in what is rendered: the text blocks
of the document (paragraphs, list items, table cells, headings, quotes)
are compared with the chunk's text, and the block sharing the most
words is scrolled to the middle and flashed (at least two shared words,
or all words of a short label; ties go to the shorter block). In a mind
map the node whose label matches the chunk's first line is flashed after
a fit. Without a real match only the tab opens.

**Reason:** a citation carries the chunk's text, not a position, and
even a position in the Markdown would not survive rendering into HTML,
a table or a markmap. The overlap uses the same word splitting as the
provenance panel's best-matching sentence, so the two agree on what
"the passage" is.

**Rejected alternative:** an exact substring search of the chunk in the
page. Rejected because chunk boundaries cut through blocks and the
rendered text drops the Markdown marks, so an exact match rarely exists.
