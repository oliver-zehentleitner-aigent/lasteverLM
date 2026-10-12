# Chunking

## One chunker in core, with regex tokens, for sources and generated documents

**Id:** 68bf3811-c6ef-4454-95d0-4b6f9200c961
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12 (agent A: the two copies in ingest and rag are identical, move them); ingest's original design of the chunker
**Revisit when:** retrieval quality points at chunk boundaries, or the embedding provider publishes a tokenizer worth depending on

`TokenWindowChunker` cuts text into windows of 800 tokens that overlap
by 100, where a token is a word or a single punctuation character found
by a regular expression. Ingest uses it on parsed sources (passages with
pages), rag on finished outputs before indexing them as generated
sources. Both call the same class from core.

**Reason:** the chunker existed twice, once per service, line for line
the same. Chunks of a generated document and chunks of a PDF land in the
same `chunks` table and are retrieved by the same query, so they must be
cut the same way, and two copies are where that stops being true. The
regex token is an approximation of a model tokenizer, good to within the
"about 800 tokens" the contract asks for; it needs no vocabulary file at
runtime and ties the family to no provider's tokenizer, which matters
because the provider is a configuration choice.

**Rejected alternative:** a model tokenizer (tiktoken or the provider's
own). More exact window sizes, rejected because it adds a vocabulary
dependency per provider to two services for a precision the contract
does not ask for.

**Rejected alternative:** keep one copy per service and let them drift.
Rejected for the reason above; ingest's own entry on the chunker
describes the original design and is superseded by this one once ingest
imports core.
