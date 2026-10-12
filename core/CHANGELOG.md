# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Keep a Changelog records what changed; [Keep the Why](https://keepthewhy.com)
preserves why it changed, in `context/`.

## [Unreleased]

## [0.1.0] - 2026-10-12

### Added

- API models of the contract v1 as Pydantic models with `UUID` ids and `datetime` timestamps; kind and status literals; `DEMO_USER_ID`.
- Bearer-token resolution `current_user`: session JWT (HS256, issuer `lasteverlm`) first, demo token second, both schemes configurable at once; `issue_jwt`, `verify_jwt`, `AuthSettings.from_env`.
- Environment helpers failing loud with `ConfigError`; `InferenceSettings.from_env`, `load_model_prices`.
- Migrations `0001_core_usage.sql` (`usage`) and `0002_core_rate_limit.sql` (`access_log`, `ip_blocks`, `ip_bans`).
- Model prices: `parse_model_prices`, `cost_cents` with exact decimal arithmetic, `require_prices`; an unpriced model raises `UnpricedModelError`.
- Provider interfaces `Embedder`, `LLM`, `TextToSpeech` reporting token usage, with OpenAI-compatible implementations and `make_client`.
- `TokenWindowChunker` with `Passage` and `Chunk`, the one chunker for parsed sources and generated documents.
- Rate limiting per client IP: `RateLimitMiddleware` (pure ASGI) over `RateLimiter` rules, stores for sync and async psycopg and in memory, `purge`, `lift_ban`, settings from the environment.
- Usage accounting `record_usage` and `balance_cents`, sync and async, over the caller's psycopg connection; the SQL exported as constants.

### Changed

- Chunker defaults are 420 regex tokens with 50 overlap (were 800/100): measured on a German PDF, the embedding model counts about 1.9 tokens per regex token, so the old window was about 1540 model tokens.
- `LLM.complete` takes `max_tokens` optionally (default `LLM_MAX_TOKENS`, 1024) and a `thinking` switch; reasoning is off by default and an empty answer without thinking is a `ProviderError`. `CompletionResult` carries `finish_reason`.
- The embedder requests `EMBEDDING_DIMENSION` from the provider on every call through the `dimensions` parameter.
- The OpenAI SDK dependency is `openai>=3`; provider tests run the SDK against a fake httpx2 transport.

### Fixed

- `make test-postgres`: the SQL paths against a throwaway pgvector container (`tests/test_postgres.py`), skipped without Docker.
- Scalar reads (`balance_cents`, the rate-limit store queries) work on connections with a `dict_row` row factory; the connection protocols accept any psycopg row type.
