# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Keep a Changelog records what changed; [Keep the Why](https://keepthewhy.com)
preserves why it changed, in `context/`.

## [Unreleased]

## [0.10.1] - 2026-10-14

### Fixed

- A PDF page whose text layer is glyph codes (a font without a usable ToUnicode map, extracted as `&MM,:N K OP&M,MM P2QL …`) no longer counts as text: a page needs at least 60 % letters among its visible characters as well as the 20-character minimum. `auto` sends such a page to the vision model, `text` skips it (and fails with "no legible text" when no page is left); the garbage used to be chunked, embedded and cited.

## [0.10.0] - 2026-10-14

### Added

- `make test-postgres`: the repository's SQL against a throwaway PostgreSQL with pgvector (`tests/test_postgres.py`): the library and its dedupe conflict, ownership on every owner-scoped call, the trash with the owner's retention, the queue (generated, trashed and backed-off rows, stale takeover, concurrent claims), the seed claim, credit and usage, the admin counts.
- PDF and text sources carry `preview_url` like images (a presigned GET of the stored original, one hour; the object's type makes the browser show a PDF in its viewer and text as `text/plain; charset=utf-8`), and URL sources carry their URL, so the library can open a document; generated rows stay `null`.

### Changed

- `GET /admin/stats` and `GET /admin/stats/daily` admit viewers as well as admins (core's `admin_read` over `admin_role`): read-only admin access for reviewers. A viewer is an ordinary user everywhere else in ingest. Needs account's `users.role` column.
- mypy runs in strict mode; the last `type: ignore` comments are gone (`record_usage` takes core's `UsageKind`, `ensure_seeded` core's `Storage`).
- Dedupe keys are built in one place (`dedupe.py`) for uploads and the demo seeds.
- PDFs of more than 2000 pages fail in every capture mode, also behind a URL, before any page is read ("PDF has N pages; at most 2000 are read"); the text layer of every page used to be extracted however many there were.
- The Dockerfile pins `python:3.13-slim` by digest (the multi-arch index) for both stages, through one `PYTHON_IMAGE` build argument; the comment says how to refresh it.

### Fixed

- A source whose worker died or hung on every attempt was taken over by the next worker after each claim timeout, without end. The claim now fails a stale row that has had three attempts ("processing did not finish in 3 attempts").
- A job that ran longer than the claim timeout (a vision PDF of many pages) could be taken over by a second worker while still running, reading and billing every page twice. The worker now refreshes its claim with every answered model call and every embedding batch.
- A multipart upload accepts one file and at most the `capture` field; more answer 400 before the parser spools them (the default allowed 1000 of each).
- A JSON body that does not parse answers 400 `body is not valid JSON` instead of 500.
- Routing errors (404 for an unknown path, 405) and the form parser's 400 use the `{"error"}` shape instead of Starlette's `{"detail"}`, and keep their headers (`Allow`).
- Documentation: the README's CI and ktw-lint badges pointed to the retired single-service repository; `docs/README.md` lacked `capture`, `demo` and `preview_url` in the source, library and trash shapes; `.env.example` lacked `IMAGE_MAX_TOKENS`, `PDF_VISION_MAX_PAGES` and `SEED_DEMO_LIBRARY`.
- The URL guard's DNS lookup was not bounded by the fetch deadline (`getaddrinfo` has no timeout); a slow resolver could hold a worker past the 30 seconds. The lookup now runs in a small thread pool and a lookup that does not answer in time is a transient failure.
- The test fake, the `has_credit` docstring and `docs/README.md` still said an admin always has credit; core changed that (15f8fa6, "admins need credit like every user"). The fake now applies core's rule and the test asserts it.

## [0.9.0] - 2026-10-13

### Added

- Image sources carry `preview_url`, a presigned GET of the stored original valid for one hour, on the notebook's source list, the library and the trash, so the frontend shows the image instead of its file name; `null` for every other kind.

## [0.7.2] - 2026-10-13

### Fixed

- Uploads write the object to the bucket before the library row: a worker could claim the row first and fail with `NoSuchKey` (the v0.7.1 smoke failure). A failed upload now answers 503 and leaves no row.
- A transient failure releases the claim with a backoff of 5 and then 15 seconds (`retry_at`, migration `0008_retry_at.sql`), so the next attempt follows promptly instead of after the 10-minute stale-claim timeout.

## [0.7.1] - 2026-10-13

### Changed

- `/healthz` answers with core's `Health`: `status`, plus `version` and `commit` from `APP_VERSION` and `APP_COMMIT`, so the admin system view shows ingest's build.

## [0.7.0] - 2026-10-13

### Added

- Demo library: every new user's library starts with four demo sources around the fictional Zeltavia (field notes PDF, glossary, map image, the Wikipedia article on dead reckoning), seeded once on the first library access or upload and processed at the demo user's expense; entries carry `demo: true`. `SEED_DEMO_LIBRARY` turns it off. Migration `0007_library_seeds.sql`.

## [0.6.0] - 2026-10-13

### Added

- PDF capture modes per upload (`capture` field: `text`, `vision`, `auto`, default `auto`): `vision` has the vision model read every rendered page (pypdfium2, 150 dpi, one billed call per page), `auto` only the pages without a text layer, so scanned and mixed PDFs work. The mode is stored on the library source and returned in sources, library and trash entries; the same bytes in two modes are two library sources. `PDF_VISION_MAX_PAGES` caps the pages per PDF (100). Migration `0006_pdf_capture.sql`.
- Library trash: `GET /library/trash` (with `deleted_at`, `purge_at`), `POST /library/{id}/restore`, `DELETE /library/{id}/purge`. Workers purge entries past the owner's `trash_days` (account preference, default 14) at start and once an hour. Migration `0005_library_trash.sql` adds `library_sources.deleted_at`.
- `GET /api/ingest/admin/stats/daily?days=30` (admins only): library sources created per UTC day by kind, and how many of them failed, every day present, oldest first.

### Changed

- Model-reading loaders bill every call as it returns through a callback, and the credit is checked before the next call (before, an image's usage was returned at the end).
- `DELETE /library/{id}` moves the entry to the trash: removed from every notebook, chunks and stored object kept until purged. Uploading the same bytes or URL again restores a trashed entry.

## [0.5.0] - 2026-10-13

### Added

- Per-user source library: `GET /library`, `GET /library/{id}` (with the notebooks each source is in) and `DELETE /library/{id}` (removes it from every notebook, chunks and stored object included). Generated outputs are never part of it.
- `POST /notebooks/{id}/sources` with `{"library_id"}` adds a library source to another notebook without uploading or processing it again.
- Uploading the same bytes (sha256) or entering the same normalised URL again links the user's existing library source: 202 with a new link, 200 with the existing one when it is already in this notebook. A failed one is queued again.
- Migration `0003_source_library.sql` (expand step): `library_sources`, `sources.library_source_id`, `chunks.library_source_id`; every existing source gets a library source with the same id.

### Changed

- `DELETE /sources/{id}` detaches the source from its notebook; it stays in the library with its chunks and stored object. Deleting a notebook detaches its sources instead of deleting their files.
- Source responses carry `library_id`. Objects of new library sources are stored at `<owner>/<library_id>/<name>`.
- The worker processes library sources once, whatever number of notebooks link them; it never claims rag's generated rows (before, it could claim one between rag creating and finishing it).

## [0.3.0] - 2026-10-13

### Added

- `GET /api/ingest/admin/stats` (admins only, core's `admin_only`): sources by status, jobs pending/running/failed, total chunks and stored bytes.
- Migration `0002_source_size.sql`: `sources.size_bytes`, written on every new source.

### Changed

- Credit checks use core's `has_credit`: admins are never out of credit, everyone else still gets 402 at zero balance.

## [0.2.1] - 2026-10-13

### Changed

- Formatting is checked with `black` (line length 100) instead of `ruff format`; `ruff check` stays the linter.

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
