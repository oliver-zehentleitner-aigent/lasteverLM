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
before `dangerouslySetInnerHTML`; every other document kind (quiz,
table, infographic, mind map outline) is rendered through React, which
escapes text. The shared page `/s/<token>` uses the same renderers.

**Reason:** the content is only as trustworthy as the sources it was
generated from, and the share page shows it to people who never logged
in. A stored-XSS path from an uploaded PDF through a report to a reader
of a shared link is exactly what sanitizing closes.

**Rejected alternative:** a Markdown-to-React renderer that never
produces an HTML string. Rejected as a larger dependency for the same
result; `marked` plus DOMPurify is small and well understood.

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
