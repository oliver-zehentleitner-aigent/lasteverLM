# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Keep a Changelog records what changed; [Keep the Why](https://keepthewhy.com)
preserves why it changed, in `context/`.

## [Unreleased]

## [0.2.0] - 2026-10-13

### Changed

- Object storage comes from core (`lasteverlm_core.storage`, shared with rag); ingest's own S3 client is gone, the `S3_*` variables are unchanged.

### Added

- URL sources: `POST /notebooks/{id}/sources` with `{"url"}` stores the URL, the worker fetches it and loads web pages (HTML text extraction), PDFs and plain text behind it. Every connection and redirect hop is checked against public addresses only.
- Image sources (PNG, JPEG, WebP, GIF, checked by their first bytes): the worker has `LLM_MODEL` transcribe the text and describe the image, bills that call as its own `usage` row, then indexes the text like any other source. `IMAGE_MAX_TOKENS` caps the answer.

### Fixed

- A blank image fails its source at once with "the image holds no readable content" instead of being retried three times, and the model call that found it empty is recorded as usage.

## [0.1.0] - 2026-10-12

### Changed

- `CHUNK_TOKENS` and `CHUNK_OVERLAP_TOKENS` are optional overrides; unset, the chunker runs with core's defaults, where the family tunes them.

- The LLM is built with `LLM_MAX_TOKENS` from core's inference settings; thinking is off for the summary (core default), so a reasoning model returns content instead of spending the budget on reasoning. The embedder requests `EMBEDDING_DIMENSION` from the model on every call (core).
- `USER 10001` in the Dockerfile, numeric so Kubernetes' `runAsNonRoot` can verify it.

- Imports models, token resolution, usage accounting, model prices and the provider implementations from `lasteverlm-core` (installed from `core/`); the local mirror `contracts.py` and the own embedder implementation are gone, the summarizer is a prompt on core's `LLM`.
- Core's `RateLimitMiddleware` is mounted outermost on the API.
- The chunker and the `Passage`/`Chunk` types come from core (`lasteverlm_core.chunking`); the service's own copy is gone.
- `INFERENCE_BASE_URL` is optional and defaults to the platform's inference endpoint.

- `make check` installs first (`make install`, `uv sync --all-extras`), so it runs on a fresh checkout and in CI.
- The migration no longer opens its own transaction; the migrations runner wraps each file in one.

### Added

- Credit check before storing, embedding and summarizing; 402 `credit exhausted` when the balance is zero.
- Dockerfile, Makefile (`check`, `run`, `build`), health endpoint on `/healthz` and `/api/ingest/healthz`.
- Embedding provider interface with an OpenAI-compatible implementation through the OpenAI SDK.
- FastAPI service implementing the ingest endpoints of the lasteverLM API contract v1.1, scoped to the bearer-token user.
- Loaders for PDF and plain text sources behind a registry open for url and image.
- Migration `db/migrations/0001_ingest.sql` for `notebooks`, `sources` and `chunks`.
- Mirror of the not yet published core library in `contracts.py` (models, token verification, accounting helpers, price parsing).
- Per-source summary written by the language model at the end of processing, accounted as a `usage` row of kind `llm`.
- S3-compatible object storage for uploads at `<notebook_id>/<source_id>/<name>`.
- Token-window chunking with overlap.
- Unit tests for chunking, loaders, pricing, token verification, the worker and the API against in-memory fakes.
- Usage accounting: one `usage` row per model call, priced from `MODEL_PRICES`; refusal to start when a configured model has no price.
- Worker entrypoint `lasteverlm-ingest-worker` that claims queued sources from PostgreSQL with `FOR UPDATE SKIP LOCKED`, counts attempts, retries transient failures by stale-claim takeover and fails a source for good on the third attempt, and stops after the current source on SIGTERM.
