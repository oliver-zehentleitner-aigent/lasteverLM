# Chunking

## Tokens are counted with a regular expression, not a model tokenizer

**Id:** 6f7a8fda-2a47-48a9-9d68-5534e25e099f
**Type:** decision
**Status:** superseded
**Superseded by:** none — the chunker moved to `core/` with its reasoning; the successor entry lives in that project, see below
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12
**See:** https://github.com/oliver-zehentleitner/lasteverLM — 68bf3811-c6ef-4454-95d0-4b6f9200c961 — as of 2026-10-12

A token for the purpose of the ~800/100 window is a word or a single
punctuation character (`\w+|[^\w\s]`). The real tokenizer of the
embedding model is not consulted. The chunker moved to `core/` on
2026-10-12 with this reasoning intact (`core/context/chunking.md`); this
service imports it and keeps no copy.

**Reason:** the contract asks for "about 800 tokens"; a word-level count
is within the tolerance that implies, and it works for every provider
the inference endpoint might serve, offline, with no vocabulary file.
The provider is an open family decision, so coupling the chunker to one
provider's tokenizer would make the chunk boundaries change with that
decision.

**Rejected alternative:** `tiktoken` (or another provider tokenizer).
Exact counts for one provider's models, rejected because it downloads
its encodings at first use — a network dependency at runtime inside the
cluster — and because the count would be wrong anyway for a model that
does not share that vocabulary. The `Chunker` interface leaves room for
a tokenizer-backed implementation if the revisit condition triggers.

### Windows may cross page boundaries

Chunks are cut over the concatenated tokens of all passages of a source,
so a window can start on one PDF page and end on the next; it carries
the page of its first token and keeps the page break as a blank line.
Not cutting at page boundaries keeps paragraphs that a layout split
across pages retrievable as one chunk; the alternative, one chunk stream
per page, was not seriously in contention because page breaks carry no
meaning for the text.
