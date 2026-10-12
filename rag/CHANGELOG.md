# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Core's rate-limit middleware in front of every endpoint (`ip_blocks`, `ip_bans`, `access_log` per the architecture).
- Answer generation over an OpenAI-compatible inference API with citations mapped back to source, chunk and page; markers naming no passage are stripped.
- Bearer token verification (JWT or shared demo token), notebook ownership check, 402 before any model call when the caller has no credit.
- Database migration `db/migrations/0001_rag.sql` for `messages` and `outputs`.
- FastAPI service for the `/api/rag` prefix: ask, messages, outputs, sharing, `/healthz` at the root and under the prefix.
- Fixed refusal with empty citations when no chunk passes the similarity floor; the model is not called.
- Generated documents: report, quiz, table, mind map, infographic through one `OutputGenerator` interface; audio prepared and failing clearly until text-to-speech exists.
- Indexing of a ready output as a source of kind `generated` in its notebook, so chat can cite it; `scope.output_id` on `/ask` restricts retrieval to it.
- Multi-stage Dockerfile with a non-root user; `make check`, `make run`, `make worker`, `make build`.
- One priced `usage` row per embedding and LLM call; startup refuses a configured model without a price.
- Retrieval over `chunks` with pgvector, scoped to one notebook and ready sources, with a configurable similarity floor.
- Sharing of a ready output through a revocable token and a read-only endpoint without authentication.
- Worker entrypoint `lasteverlm-rag-worker` that claims output jobs from the `outputs` table with `FOR UPDATE SKIP LOCKED`, so API pods stay stateless and workers scale on their own.
- Unit tests with mocked store, retriever and providers for citation mapping, the refusal path, credit, pricing, the output lifecycle, sharing and the generators' schemas.

### Changed

- An unscoped `/ask` retrieves from the uploaded sources only; generated documents restate them and are reached through `scope.output_id`. `RETRIEVAL_INCLUDE_GENERATED=true` restores the previous behaviour.
- Generators are told to title the document by its subject and form, never with the notebook's name (the first live run produced four documents named after the notebook).
- The worker closes its connection pool on shutdown and logs every finished output.
- A model reply without content (a reasoning model that spent its budget on thinking) is a provider failure: `/ask` answers 502 and stores no message, a generation is retried by the worker; never an empty answer.
- The LLM is constructed with `LLM_MAX_TOKENS` as its default budget and called with thinking disabled (core's default) for answers and generators; the generator call-back carries core's `complete` signature.
- Generated documents are chunked with `lasteverlm_core.chunking`, the family's one chunker; the local copy is gone.
- Shared API models, bearer-token resolution, pricing, usage accounting and the provider adapters come from `lasteverlm_core` (installed by path from `../core`); the local mirror is gone.
