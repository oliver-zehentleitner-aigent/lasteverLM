# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Keep a Changelog records what changed; [Keep the Why](https://keepthewhy.com)
preserves why it changed, in `context/`.

## [Unreleased]

### Added

- API models of the contract v1 as Pydantic models with `UUID` ids and `datetime` timestamps; kind and status literals; `DEMO_USER_ID`.
- Bearer-token resolution `current_user`: session JWT (HS256, issuer `lasteverlm`) first, demo token second, both schemes configurable at once; `issue_jwt`, `verify_jwt`, `AuthSettings.from_env`.
- Environment helpers failing loud with `ConfigError`; `InferenceSettings.from_env`, `load_model_prices`.
- Migrations `0001_core_usage.sql` (`usage`) and `0002_core_rate_limit.sql` (`access_log`, `ip_blocks`, `ip_bans`).
- Model prices: `parse_model_prices`, `cost_cents` with exact decimal arithmetic, `require_prices`; an unpriced model raises `UnpricedModelError`.
- Provider interfaces `Embedder`, `LLM`, `TextToSpeech` reporting token usage, with OpenAI-compatible implementations and `make_client`.
- `TokenWindowChunker` (800 tokens, 100 overlap) with `Passage` and `Chunk`, the one chunker for parsed sources and generated documents.
- Rate limiting per client IP: `RateLimitMiddleware` (pure ASGI) over `RateLimiter` rules, stores for sync and async psycopg and in memory, `purge`, `lift_ban`, settings from the environment.
- Usage accounting `record_usage` and `balance_cents`, sync and async, over the caller's psycopg connection; the SQL exported as constants.

### Fixed

- Scalar reads (`balance_cents`, the rate-limit store queries) work on connections with a `dict_row` row factory; the connection protocols accept any psycopg row type.
