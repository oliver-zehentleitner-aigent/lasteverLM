# Providers

## Embeddings ask for their width; completions run with reasoning off

**Id:** b9d85733-8d1c-4e09-ac53-cb9303f871b0
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** probe of the inference platform, 2026-10-12 (models list, embeddings with and without `dimensions`, six completion variants); infra's first real run reported by agent A
**Revisit when:** the embedding or language model changes, or the provider stops honouring `dimensions` or `chat_template_kwargs`

The embedder sends `dimensions=EMBEDDING_DIMENSION` on every request and
refuses a vector of another width. The language model provider sends
`chat_template_kwargs: {"enable_thinking": false}` unless the instance or
the call asks for `thinking=True`; with thinking off, an empty answer is
an error. `max_tokens` defaults to `LLM_MAX_TOKENS` (1024).

**Reason:** two facts of the platform, both measured. The only embedding
model returns 2560 dimensions natively, above the 2000 that pgvector can
index; the API honours the OpenAI `dimensions` parameter and returned
1024 when asked. The language model is a reasoning model: with
`max_tokens=40` the content came back empty, `finish_reason` was
`length` and 39 of 40 completion tokens were reasoning; with a budget of
400 the answer arrived after the thinking, prefixed by a blank line. The
family's prompts (source summaries, cited answers with `[n]` markers,
output generators) are extraction over given text and gain nothing from
hidden reasoning, while every reasoning token is billed. Off is the
default; a generator that wants it can ask.

**Rejected alternative:** a large default `max_tokens` and thinking left
on. Rejected because the thinking is paid for on every call and the
answer still depends on the budget not running out mid-thought.

**Rejected alternative:** `reasoning_effort: "none"` or
`reasoning: {"enabled": false}` as the switch. Both worked on the platform
too; `chat_template_kwargs.enable_thinking` is the one the model
family's own serving stack documents, so it is the one sent. A top-level
`enable_thinking` was ignored. The switch is one function
(`thinking_body`), so changing it is one line.

**Rejected alternative:** let callers pass raw `extra_body`. Rejected
because the provider's quirks then leak into three services; the
interface stays `complete(system, user, max_tokens, thinking=)`.

## An unusable embedding vector fails the call

**Id:** 3310d44f-d79f-4da6-abdc-ad94e857529c
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** rag's request after a ready PDF whose chunks never came back in retrieval, 2026-10-13 (cause not proven); pgvector's cosine distance against a zero or non-finite vector is NaN
**Revisit when:** the platform is shown to return such vectors for a legitimate input class that should be indexed anyway

`OpenAICompatibleEmbedder.embed` raises `ProviderError` when a vector
has a NaN or infinite component or a zero norm, naming the input index.
The check runs after the count and width checks, in pure Python.

**Reason:** such a vector is stored without complaint but can never be
found. Its cosine distance is NaN, the similarity floor drops it, and the
source stays `ready` while nothing in it is searchable. An error makes
ingest fail that source visibly and turns a bad query or output embedding
in rag into a 502 or a retry. Any of those beats a silent gap.

**Rejected alternative:** skip the bad vector and store the rest. The
source would look complete with a hole in it, the same silence on a
smaller scale.

**Rejected alternative:** a check in SQL or in each service. Every
service would need it; the embedder is the one place all vectors pass.
