# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Keep a Changelog records what changed; [Keep the Why](https://keepthewhy.com)
preserves why it changed, in `context/`.

## [Unreleased]

## [0.6.0] - 2026-10-13

### Added

- Preference `trash_days` (1–365, null = 14): how long a deleted library entry stays in the trash before ingest purges it.

### Added

- Per-user preferences `ui_language`, `output_language`, `audio_voice` (migration 0005, jsonb on `users`): `GET/PUT /me/preferences` (partial update, null clears), carried on `User` so the web has them at login; the shared demo user cannot change them.

### Added

- Chart data for the admin overview: `GET /admin/stats/daily?days=` (logins, visits, usage cost and credits granted per UTC day, every day present, zeros included, oldest first) and `GET /admin/stats/usage` (core's usage rows by model and kind, the ten users with the highest usage).

### Added

- `granted_cents` on each row of `GET /admin/users` (the user's ledger sum), so the "credits granted" tile can be broken down per user.

### Changed

- `GET /admin/stats` counts the seeded demo user in `users`, as `GET /admin/users` lists it and `credits_granted_cents` includes its seed; one rule for both.

## [0.4.0] - 2026-10-13

### Added

- `GET/PUT/DELETE /admin/settings/ratelimit`: the rate-limit rule in force; PUT overrides per_minute, block_minutes, ban_after_strikes and strike_window_hours for every service (core's `ratelimit` settings key and bounds, 422 outside them), DELETE returns to the environment defaults; `ban_max_days` and `retention_days` are shown read-only.

- Sign-in attempts: `login_attempts` (migration 0004) records every request for a link with e-mail, plain client IP and outcome allowed|refused; `GET /admin/login-attempts?limit=` lists them newest first; purged after `RETENTION_DAYS` at start like the access log.

- `DELETE /admin/vouchers/{id}` removes an open voucher; a redeemed one answers 409, it is history and backs a ledger row.

## [0.3.0] - 2026-10-13

### Added

- Single addresses in the allowlist next to domains (`allowed_addresses` setting); `GET /admin/settings/allowlist` returns both lists, `POST`/`DELETE` per entry under `/admin/settings/domains` and `/admin/settings/addresses`.
- `GET /admin/vouchers?limit=` lists vouchers newest first with creator and redeemer as e-mail and a `status`; the code is never listed, only its hash is stored.
- `GET /admin/stats`: users, logins last 24 h, vouchers issued/redeemed/open, credits granted, usage cost total and last 24 h (core's `usage` rows), active blocks and bans.
- Error bodies carry a stable `code` where a client must tell refusals apart; the first is `not_allowed`.

### Changed

- `POST /auth/request-link` answers 403 `not_allowed` for an address that may not sign in instead of a silent 202; no mail is sent for it either way.

### Removed

- `PUT /admin/settings/domains`; entries are added and removed one at a time.

## [0.2.1] - 2026-10-13

### Changed

- SMTP configuration comes from the environment only (`SMTP_*`, Secret `lasteverlm-smtp`), read at start; `GET /admin/settings/smtp` shows it read-only, never the password. A `settings.smtp` row left from before is deleted at start so the old password does not linger.
- Code is formatted with black (line length 100, family-wide decision); `make lint` runs `black --check` next to `ruff check`.

### Fixed

- Docs and context name the SMTP Secret `lasteverlm-smtp`, as infra calls it since the rename.

### Removed

- `PUT /admin/settings/smtp` and the SMTP seed into the `settings` table.

## [0.2.0] - 2026-10-13

### Changed

- A ban holds until an admin lifts it, at most `BAN_MAX_DAYS` (90): the startup purge follows core's new `purge_params` (both cutoffs) instead of a single cutoff.

### Added

- Retention of core's rate-limit tables (`access_log`, stale `ip_blocks`, lifted `ip_bans`) at every start, `RETENTION_DAYS` (30); active bans stay. Core's middleware writes those tables and nobody purged them before.

### Changed

- Core's rate-limit store gets the repository's pooled connections directly; the tuple-row detour is gone since core reads scalars independently of the row factory.

## [0.1.0] - 2026-10-12

### Added

- `VISIT_HASH_SECRET`: optional shared secret so all replicas derive the same daily visitor salt (`HMAC(secret, date)`).
- Core's `RateLimitMiddleware` as the outermost layer: 429 and blocks, 403 for banned addresses, one `access_log` row per request.
- `make install` (`uv sync --all-extras`, idempotent); `make check` depends on it and works on a fresh checkout.
- Access control for admins: current blocks, bans with lifting, the access log written by core's rate-limit middleware.
- Admin backend: SMTP and domain settings, users, logins, vouchers, visitor statistics per day and path.
- Credits: single-use vouchers, ledger, balance as ledger minus usage.
- Development entrypoint `make run-dev` with in-memory storage and console mail, for frontend work without PostgreSQL.
- Dockerfile (port 8000, non-root), health endpoint, Makefile with `check`, `run`, `build`.
- FastAPI service implementing the account endpoints of the lasteverLM API contract v1.
- Passwordless magic-link login restricted to allowed e-mail domains; HS256 session tokens.
- PostgreSQL migrations for the account tables and the seeded demo user with its initial credit.
- Unit tests against an in-memory repository (token flow, allowlist, voucher atomicity, balance, admin gate, privacy); optional PostgreSQL integration tests.
- Visitor log without personal data: daily-rotating salted IP hash, browser family only, 30 days retention.

### Fixed

- An empty persisted allowlist is re-seeded from a non-empty `AUTH_ALLOWED_DOMAINS` at startup instead of locking the deployment for good.
- Startup log always states the settings seed, retention counts and salt mode; a deployment nobody can log in to is warned about.
- Dockerfile sets `USER 10001` by uid, which Kubernetes' `runAsNonRoot` can verify; a user name cannot be checked at admission.

### Changed

- `contracts.py` removed; `User`, `AdminUser`, token issue and resolution and the demo identity come from `lasteverlm-core`, installed by path from `../core`.
- `make run` and the image start the app through `uvicorn --factory lasteverlm_account.main:create_app`.
- Lifting a ban uses core's statement, so the admin action and the middleware agree.
