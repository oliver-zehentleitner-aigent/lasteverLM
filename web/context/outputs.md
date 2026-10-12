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
