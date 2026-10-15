# Chunking

## One chunker in core, with regex tokens, for sources and generated documents

**Id:** 68bf3811-c6ef-4454-95d0-4b6f9200c961
**Type:** decision
**Status:** superseded
**Superseded by:** dc660692-6bb2-4ecb-8472-f90b6297763c
**Evidence:** confirmed
**Source:** a comparison of the two copies in ingest and rag, found identical, 2026-10-12; ingest's original design of the chunker
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

## Windows of 420 regex tokens: the regex undercounts German by half

**Id:** dc660692-6bb2-4ecb-8472-f90b6297763c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** ingest live run, 2026-10-12 (51-page German PDF: 66232 embedding tokens over 43 chunks of 800 regex tokens)
**Revisit when:** retrieval quality points at chunk boundaries, the embedding model changes, or sources are mostly in a language other than German or English

`TokenWindowChunker` defaults to windows of 420 regex tokens with an
overlap of 50. Rag uses the defaults. Ingest uses them too unless
`CHUNK_TOKENS` or `CHUNK_OVERLAP_TOKENS` is set; the deployment sets
neither. The
regex token (a word or a punctuation character) stays.

**Reason:** the previous defaults, 800 and 100, assumed a regex token is
about a model token. Measured on a real German document, the embedding
model counted about 1540 tokens per 800-regex-token chunk, 1.9 to one,
because German compounds and inflections split into several subword
tokens. Rag's top-8 context was therefore about 12k model tokens where
the contract intends about 6k. 420 regex tokens land near 800 model
tokens for German and near 550 for English; the German case is the one
the deployment serves, and a somewhat small English window costs
retrieval little, while a window twice the intended size doubles the
prompt and its price on every question.

**Rejected alternative:** count with the model's own tokenizer. Exact,
and still the right move if chunk boundaries ever show up in retrieval
quality; rejected for now because it adds a vocabulary dependency per
provider to two services, while a corrected constant removes the
measured error for the languages in use. This supersedes the previous
entry's defaults, not its choice of the regex token.
