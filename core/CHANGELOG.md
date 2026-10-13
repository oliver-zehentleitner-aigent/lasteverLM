# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Keep a Changelog records what changed; [Keep the Why](https://keepthewhy.com)
preserves why it changed, in `context/`.

## [Unreleased]

## [0.4.0] - 2026-10-13

### Added

- Runtime rate-limit rules: the limiter overrides `per_minute`, `block_minutes`, `ban_after_strikes` and `strike_window_hours` from account's `settings` row `ratelimit` (jsonb), re-read at most every 30 s per process; env values stay the defaults, an unusable row falls back to them with one warning. `RateLimitRules` (`parse`, `from_settings`, `as_json`), `RATE_LIMIT_SETTINGS_KEY`, `RATE_LIMIT_RULE_BOUNDS`, `RULES_TTL_SECONDS`, `RULES_SQL`; `RateLimiter.rules` and `current_rules`; stores gain `rule_overrides`.

## [0.3.1] - 2026-10-13

### Changed

- `has_credit` / `ahas_credit` no longer exempt admins: the check is `balance_cents > 0` for every user. `is_admin`, `ais_admin` and `admin_only` are unchanged and gate only the admin endpoints.

## [0.3.0] - 2026-10-13

### Added

- `has_credit` / `ahas_credit`: the pre-call check, true for an admin whatever the balance and for anyone else with `balance_cents > 0`; replaces `balance_cents(...) <= 0` in the services. Admins are still billed.
- `is_admin` / `ais_admin`: `users.is_admin` per request (no JWT claim); a user without a row is no admin. `HAS_CREDIT_SQL`, `IS_ADMIN_SQL` exported.
- `lasteverlm_core.web.admin_only(current_user, lookup)`: FastAPI dependency for admin-only endpoints, 403 `admin only` for non-admins; the `web` extra names FastAPI.

## [0.2.1] - 2026-10-13

### Changed

- black is the formatter (`[tool.black]`, line length 100, `black --check` in `make lint`); ruff stays the linter. No code changed: ruff's format output was already black-compatible.

## [0.2.0] - 2026-10-13

### Added

- `lasteverlm_core.storage`: `S3Storage` with put, get, delete and `presigned_get(key, expires_s=3600)` (SigV4), `S3Settings.from_env`, `object_key`, the `Storage` protocol; moved from ingest so that ingest and rag share one S3 client. New dependency `boto3`.
- `purge_params(retention_days, ban_max_days)` and the package-level export of `PURGE_SQL`, so an async caller runs the purge statements with the same parameters as `purge`.
- Usage kind `tts`, priced per input character (`tokens_in` = characters, `tokens_out` = 0); migration `0003_core_usage_tts.sql` widens the check on `usage.kind`.

### Changed

- `OpenAICompatibleTextToSpeech` defaults to the platform voice `ryan` (`DEFAULT_TTS_VOICE`); the OpenAI name `alloy` is rejected by the platform.
- An active ban holds until an admin lifts it, for at most `BAN_MAX_DAYS` (default 90): the limiter treats an older ban as expired and the purge deletes it, lifted or not. `PURGE_SQL` takes `cutoff` and `ban_cutoff`; `purge` gains `ban_max_days`. The store methods take the limiter's clock: `is_banned(ip, since)`, `ban(ip, reason, now)`.

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
