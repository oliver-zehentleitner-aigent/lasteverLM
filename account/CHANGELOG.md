# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Keep a Changelog records what changed; [Keep the Why](https://keepthewhy.com)
preserves why it changed, in `context/`.

## [Unreleased]

### Added

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

### Changed

- `contracts.py` removed; `User`, `AdminUser`, token issue and resolution and the demo identity come from `lasteverlm-core`, installed by path from `../core`.
- `make run` and the image start the app through `uvicorn --factory lasteverlm_account.main:create_app`.
- Lifting a ban uses core's statement, so the admin action and the middleware agree.
