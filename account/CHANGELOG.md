# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Keep a Changelog records what changed; [Keep the Why](https://keepthewhy.com)
preserves why it changed, in `context/`.

## [Unreleased]

### Added

- `GET /api/account/prices`, the public price list (no login, five-minute cache): per action the unit (core's `USAGE_ACTION_UNITS`), price per unit, p25/median/p75 per action and the model, from the last 30 days' measured costs through today's rules (core's `charge_for`); no number below five actions; end prices only.

### Added

- The exchange rate follows the ECB: every hour the service reads the daily euro reference rate for USD and writes it into the pricing rules when it changed; a failed fetch keeps the rate and is shown; the pricing view reports `rate` (value, mode, source, ECB date, last check, last success, error, stale after three days). An admin's own rate switches to manual and pauses the update; `PUT /admin/settings/pricing/rate-mode`, `POST /admin/settings/pricing/rate/sync`. `EXCHANGE_RATE_SYNC` turns the loop off for offline runs.

## [0.18.0] - 2026-10-14

### Added

- Migration 0010 seeds the pricing row core's booking needs: `usd_per_eur` 1.1188 (ECB reference rate of 2026-10-13, until the maintainer confirms one), no margin, no fees; an existing row is never touched.
- Pricing and finance on core's split of cost and charge (core #394): `GET/PUT/DELETE /admin/settings/pricing` and `POST /admin/settings/pricing/preview` (core's rules, an example charge per action from the last 30 days), `GET /admin/finance/costs` (group by day, action, model, user, service; real cost in EUR and the measured USD), `/admin/finance/revenue` (charged, paid vs. free vouchers, credit outstanding, demo apart), `/admin/finance/profit` (charged − model cost − infrastructure per day or month).
- Infrastructure costs for the finance pages (migration 0009, `infra_costs`): a daily Vultr billing sync inside the service with `VULTR_BILLING_API_KEY` (pending charges and the last three invoices, monthly lines in USD, idempotent), manual entries, `GET/POST /admin/finance/infra`, `DELETE /admin/finance/infra/{id}`, `POST /admin/finance/infra/sync`; without a key the API says `"vultr": "not connected"`. USD lines are converted at the pricing rules' `usd_per_eur`; EUR figures stay null without a rate.
- Vouchers carry `paid` (default false; on create and via `PATCH /admin/vouchers/{id}`).
- Voucher codes stay recoverable for admins: new vouchers store the code AES-GCM-encrypted under `VOUCHER_KEY` (required, 32 bytes base64; migration 0008 adds `code_enc`, `sent_to`, `sent_at`). `GET /admin/vouchers/{id}/code` shows it (admin only), the list shows it masked with `recoverable`, `sent_to`, `sent_at`.
- `POST /admin/vouchers/{id}/send` `{email, message?, allow?}` mails a voucher with the sign-in link (German or English by the sending admin's `ui_language`), adds the address to the allowlist first unless `allow` is false, records `sent_to`/`sent_at`; 409 `already_redeemed`, 429 `too_many_mails` (5 per address per hour), 502 `mail_failed`. `POST /admin/vouchers` takes the same `send_to`, `message`, `allow` to send each created voucher right away.
- `viewer_addresses` beside `viewer_domains`: a first sign-in of a listed address gets the viewer role (`POST/DELETE /admin/settings/viewer-addresses`, listed in `GET /admin/settings/allowlist`); the address must be allowed to sign in as well, existing users keep their role.

### Changed

- `ban_max_days` (1–365) is part of the editable rate-limit rule: `PUT /admin/settings/ratelimit` accepts it (omitted keeps the `BAN_MAX_DAYS` default), core's limiter and the startup purge use the stored value (core #387).
- Balances are credits minus what users were charged (`usage.charge_cents`, falling back to the cost for rows booked before core 0006), rounded down to whole cents; the users list shows charges rounded up. `/admin/stats` keeps real cost.
- Vouchers created before this release exist only as hashes: their codes cannot be shown or sent again (404 `not_recoverable`). They stay redeemable.

## [0.14.0] - 2026-10-14

### Changed

- `/healthz` reports `dependencies: {"postgres": "ok"|"down"}` through core's `DependencyProbe` (2 s timeout, 15 s cache) and no longer fails when the database is away: the status says the process answers, the dependency state says what is wrong. `/admin/system` shows the same states for account.

### Added

- `GET /admin/system` for the live architecture diagram: `dependencies` per service (passed through from its healthz), `phase`, `reason` (container waiting/terminated reason) and `template_hash` per pod, `progressing`, `available` and `replica_sets` (ReplicaSets with pods, from the pods' template hashes — no new RBAC) per deployment.

## [0.12.0] - 2026-10-14

### Changed

- One way to reach ingest and rag: `INGEST_URL` and `RAG_URL` serve the System page's health probes (`/healthz` appended) and the user purge; `SYSTEM_SERVICES` is gone.

### Added

- `DELETE /admin/users/{id}`: orchestrated hard delete — rag and ingest purge the user's data on the admin's bearer (`RAG_URL`, `INGEST_URL`), then account deletes the user, ledger, login log, usage rows and the visit log's reference; vouchers and `login_attempts` stay as history (migration 0007 lets a voucher outlive its creator). 409 for the caller's own account and the demo user; 502 `purge_failed` with the step when another service fails, nothing deleted then.

## [0.10.0] - 2026-10-14

### Changed

- Dockerfile pins `python:3.13-slim` by digest (the multi-arch index) in both stages; the refresh command is in the file.
- Session tokens live one day by default (`JWT_TTL_DAYS=1`, was 7); sign-out is client-side, SECURITY.md says so.
- Lifting a ban: `DELETE /admin/bans?ip=<key>` takes the key as a query parameter because IPv6 bans are keyed by a /64 prefix, which carries a slash; the path form stays for IPv4 one release, deprecated.
- The client address for visits and sign-in attempts is resolved by core's `client_ip`, the same way the rate-limit middleware does; a malformed `X-Forwarded-For` becomes `0.0.0.0` instead of a failed insert.
- `output_language` is capped at 35 characters, the callback token at 512; the OpenAPI version is `APP_VERSION`.

### Added

- Roles `user` | `viewer` | `admin` (migration 0006, `users.role`; `is_admin` stays equal to `role = 'admin'`): a viewer reads every `GET` under `/admin`, writes stay admin only; `User` and the admin user rows carry `role`; `PATCH /admin/users/{id}` sets it (409 for the last admin or the demo user); `viewer_domains` in the allowlist (`POST/DELETE /admin/settings/viewer-domains`) makes a first sign-in from a listed domain a viewer.
- Per-address quota for sign-in links: more than `LINK_QUOTA_PER_HOUR` (5) within an hour answers 429 with `code: too_many_links` and a readable sentence; counted on `login_attempts`, a throttled request writes no row.

### Removed

- The service's own `client_ip`, the unused `ErrorResponse` model, the stale `__version__` constant, the whole-list `set_allowed_domains` helper.

### Fixed

- SECURITY.md described the login as never revealing the allowlist and the service as unlimited; both were stale since the `not_allowed` answer and core's middleware.

## [0.8.0] - 2026-10-13

### Added

- Preference `theme` (system|light|dark, null = system); the web applies it.

## [0.7.0] - 2026-10-13

### Added

- `GET /admin/system` for the admin System page: `APP_VERSION`/`APP_COMMIT`, every service's health with version and commit (probed over the cluster DNS, `SYSTEM_SERVICES`), and the namespace's pods and deployments read from the Kubernetes API with the pod's ServiceAccount; outside a cluster `cluster: false` with empty lists. `/healthz` reports version and commit too.

### Changed

- The sign-in mail offers the token as a code to paste on the sign-in page, after the link; one note covers both (single use, 15 minutes). Subject unchanged.

## [0.6.0] - 2026-10-13

### Added

- Preference `pdf_capture` (auto|text|vision, null = auto): the default capture mode for PDF uploads; the web sends the resolved value per upload.
- Preference `trash_days` (1–365, null = 14): how long a deleted library entry stays in the trash before ingest purges it.
- Per-user preferences `ui_language`, `output_language`, `audio_voice` (migration 0005, jsonb on `users`): `GET/PUT /me/preferences` (partial update, null clears), carried on `User` so the web has them at login; the shared demo user cannot change them.
- Chart data for the admin overview: `GET /admin/stats/daily?days=` (logins, visits, usage cost and credits granted per UTC day, every day present, zeros included, oldest first) and `GET /admin/stats/usage` (core's usage rows by model and kind, the ten users with the highest usage).
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
- Core's rate-limit store gets the repository's pooled connections directly; the tuple-row detour is gone since core reads scalars independently of the row factory.

### Added

- Retention of core's rate-limit tables (`access_log`, stale `ip_blocks`, lifted `ip_bans`) at every start, `RETENTION_DAYS` (30); active bans stay. Core's middleware writes those tables and nobody purged them before.

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

