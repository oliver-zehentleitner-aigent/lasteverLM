# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.3] - 2026-10-13

### Fixed

- A generated document could cover one source only: the generator's passages were a global top-k that one source could fill. Retrieval for generators now keeps each ready source's best chunks and fills the rest by score; the prompts require every source to be covered (the mind map's root spans them), and a source the document never mentions is logged as a warning.

## [0.7.1] - 2026-10-13

### Changed

- `/healthz` answers core's `Health` (`status`, `version`, `commit` from `APP_VERSION` / `APP_COMMIT`), so the admin system view shows rag's build.

## [0.7.0] - 2026-10-13

### Added

- `POST /api/rag/outputs/voice-sample`: a short preview of a voice at a speed and in a language, synthesized once and then served from storage.

## [0.6.0] - 2026-10-13

### Added

- Citations carry their provenance: `similarity` (the chunk's score for the question), `chunk_index` and `chunk_count`; persisted messages keep them.
- `GET /api/rag/chunks/{chunk_id}`: the exact chunk behind a citation, for its owner.
- Output options: `language` for every kind, `voice` and `speed` for audio, validated per kind, stored on the output (migration `0003_rag_output_options.sql`) and returned as `options`; `GET /api/rag/outputs/options` serves the catalogue.
- `GET /api/rag/admin/stats/daily?days=30` for the admin charts: messages and outputs (total and by kind) per UTC day, every day present.

### Changed

- A citation's `quote` is the verbatim chunk text; it was cut at 300 characters before.
- `TTS_VOICE` must be one of the platform's voices; startup refuses any other.

## [0.5.0] - 2026-10-13

### Changed

- Retrieval, the output queue's gate and the generator input read sources through ingest's source library (`sources` link → `library_sources` → `chunks`); the source id in answers stays the link's.
- A generated output is indexed as a hidden `generated` library row plus its link, created in one transaction and deleted with the output.

## [0.4.0] - 2026-10-13

### Added

- Conversations: several chats per notebook (`GET`/`POST /api/rag/notebooks/{id}/conversations`, `DELETE /api/rag/conversations/{id}`, `GET /api/rag/conversations/{id}/messages`); migration `0002_rag_conversations.sql` moves existing history into `Chat 1`.
- The model sees the newest six messages of the conversation, so a follow-up question can refer to an earlier turn.

### Changed

- `POST .../ask` requires `conversation_id` (422 without it); `GET /api/rag/notebooks/{id}/messages` is removed in favour of the per-conversation list.
- Admins need credit like every user again (core's `has_credit` dropped the admin exemption); README and tests follow.

## [0.3.0] - 2026-10-13

### Added

- `GET /api/rag/admin/stats` for admins: notebooks, messages (total, last 24 h), outputs by kind and by status, jobs pending, running and failed, shared outputs.

### Changed

- The credit check is core's `has_credit`: admins have unlimited credit; everyone else still gets 402 at a zero balance.

## [0.2.1] - 2026-10-13

### Changed

- Formatting is black's (line length 100); `make lint` runs `black --check` and keeps `ruff check` for linting.

## [0.2.0] - 2026-10-13

### Added

- Audio output: an LLM-written spoken-word script, synthesized with `TTS_MODEL` and `TTS_VOICE` (default `ryan`) in sentence-boundary segments, stored as one MP3 in object storage and served as a presigned URL valid for one hour; one `tts` usage row per segment.

### Changed

- Deleting an output also deletes its stored files.

## [0.1.0] - 2026-10-12

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

- Citations are contract-clean: grouped markers become single `[n]` markers and `n` is renumbered densely in order of first appearance after made-up markers are dropped.
- A scoped `/ask` retrieves without a similarity floor and with k=12 over its one document, so a summary-type question is answered.
- An unscoped `/ask` retrieves from the uploaded sources only; generated documents restate them and are reached through `scope.output_id`. `RETRIEVAL_INCLUDE_GENERATED=true` restores the previous behaviour.
- Generators are told to title the document by its subject and form, never with the notebook's name (the first live run produced four documents named after the notebook).
- The worker closes its connection pool on shutdown and logs every finished output.
- A model reply without content (a reasoning model that spent its budget on thinking) is a provider failure: `/ask` answers 502 and stores no message, a generation is retried by the worker; never an empty answer.
- The LLM is constructed with `LLM_MAX_TOKENS` as its default budget and called with thinking disabled (core's default) for answers and generators; the generator call-back carries core's `complete` signature.
- Generated documents are chunked with `lasteverlm_core.chunking`, the family's one chunker; the local copy is gone.
- Shared API models, bearer-token resolution, pricing, usage accounting and the provider adapters come from `lasteverlm_core` (installed by path from `../core`); the local mirror is gone.
