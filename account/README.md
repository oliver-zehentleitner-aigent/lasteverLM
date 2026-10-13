# account

[![ci](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

The account service of [lasteverLM](../README.md), a NotebookLM-style
assistant, in the `account/` directory of the one repository. It owns who may use the system and what they
may spend: passwordless magic-link login restricted to allowed e-mail
domains, session tokens the other services verify, prepaid credits via
single-use vouchers, the admin panel backend (domain settings, the mail
configuration read-only, users, logins, vouchers) and a visitor log that stores no personal data.

The API contract this service implements is
[`docs/architecture.md`](../docs/architecture.md) at the repository root,
prefix `/api/account`. Changes to the contract are made there first.

- How to operate it: [`docs/operations.md`](docs/operations.md)
- Why it is built this way: [`context/index.md`](context/index.md)

## API, prefix `/api/account`

`User` carries `preferences` `{ui_language: de|en|null, output_language: <language code>|null,
audio_voice: <voice id>|null}`; `null` means not set (the web's default language, the
source's language, the platform's default voice). `PUT /me/preferences` takes any subset:
a key with a value sets it, with `null` clears it, an absent key is kept. Validation is by
shape only; which voices and output languages exist is rag's business.

`GET /admin/stats` is the admin overview: users, logins and usage cost of the last
24 h, vouchers issued/redeemed/open, credits granted (the ledger sum), active blocks
and bans. The seeded demo user is a row in `GET /admin/users` and counts in both
numbers: it holds and spends credit like anyone else, and `granted_cents` per user
adds up to the tile this way. Usage cost comes from core's `usage`
rows, which ingest and rag write.

| Area | Endpoints |
|---|---|
| Login | `POST /auth/request-link` (202 for an allowed address, 403 with `code: not_allowed` for any other, no mail either way for the latter), `GET /auth/callback?token=` → `{jwt, user}` |
| Account | `GET /me` → `User` (with `preferences`), `GET /me/preferences`, `PUT /me/preferences` (partial, returns `User`; the demo user gets 403), `POST /vouchers/redeem` → `User`, `POST /visits` (204, works without a token) |
| Admin | `GET /admin/users`, `GET /admin/logins?limit=`, `GET /admin/login-attempts?limit=` (allowed and refused link requests, with client IP), `GET /admin/visits?days=`, `GET /admin/settings/smtp` (read-only), `POST /admin/settings/smtp/test`, `GET/PUT/DELETE /admin/settings/ratelimit` (the rule in force; PUT overrides the four runtime fields for every service, DELETE returns to the environment defaults), `GET /admin/settings/allowlist` → `{allowed_domains, allowed_addresses}` (same at `/settings/domains` and `/settings/addresses`), `POST /admin/settings/domains` `{domain}` / `DELETE /admin/settings/domains/{domain}`, `POST /admin/settings/addresses` `{address}` / `DELETE /admin/settings/addresses/{address}` (201 with both lists, 204; 409 already listed, 404 not listed), `GET /admin/vouchers?limit=` (newest first, no codes), `POST /admin/vouchers`, `DELETE /admin/vouchers/{id}` (204 open, 409 redeemed), `GET /admin/stats`, `GET /admin/stats/daily?days=` (per UTC day, every day present, oldest first), `GET /admin/stats/usage` (by model and kind, top 10 users) |
| Access control | `GET /admin/blocks`, `GET /admin/bans?include_lifted=`, `DELETE /admin/bans/{ip}`, `GET /admin/access?limit=` |
| Health | `GET /healthz`, also at the server root for the Kubernetes probe |

Errors are `{"error": "<message>"}`, with a stable `"code"` where a client
has to tell refusals apart (today only `not_allowed`): 401 unauthenticated,
403 not admin or an address without access, 404 unknown or used voucher,
no active ban or allowlist entry not listed, 409 SMTP not configured or
allowlist entry already listed, 422 bad request or malformed entry, 502
mail could not be sent.

Who may sign in: an address listed in `allowed_addresses`, an address
whose domain is listed in `allowed_domains`, or an address in
`ADMIN_EMAILS`. Both lists are edited in the admin panel one entry at a
time; `AUTH_ALLOWED_DOMAINS` only seeds the domain list. With both lists
empty nobody but the configured admins can sign in.

Rate limiting and blocking happen in `RateLimitMiddleware` from
[`core/`](../core/), mounted as the outermost layer of this service as of
every API service: too many requests from one address give 429 and a
15-minute block, the third block within 24 hours a ban (403 on
everything). The admin endpoints `/admin/blocks`, `/admin/bans` and
`/admin/access` show the result and let an admin lift a ban.

The first user who ever logs in becomes admin, as does every address in
`ADMIN_EMAILS`. A balance is `sum(ledger) - sum(usage)`; the `usage` rows
are written by the ingest and rag services and only read here.

## Configuration

Everything comes from the environment; the service refuses to start when
a required value is missing. `.env.example` has every variable with a
comment.

| Variable | Required | Meaning |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL connection string (Kubernetes secret `lasteverlm-db`) |
| `AUTH_JWT_SECRET` | yes | HS256 secret for session tokens, shared with ingest and rag (`lasteverlm-auth`) |
| `PUBLIC_BASE_URL` | yes | base of the link in the sign-in mail (`lasteverlm-config`) |
| `DEMO_TOKEN` | no | shared demo token; unset in production (`lasteverlm-auth`) |
| `ADMIN_EMAILS` | no | comma-separated admin addresses, may log in regardless of the allowlist (`lasteverlm-account`) |
| `AUTH_ALLOWED_DOMAINS` | no | seed for the allowlist, first start only (`lasteverlm-account`) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, `SMTP_STARTTLS` | no | the mail configuration, read at start and shown read-only in the admin panel, never stored; without `SMTP_HOST` no sign-in mail can be sent (`lasteverlm-smtp`) |
| `MAGIC_LINK_TTL_MINUTES`, `JWT_TTL_DAYS`, `VOUCHER_DEFAULT_CENTS`, `VISIT_RETENTION_DAYS`, `TRUST_PROXY_HEADERS`, `LOG_LEVEL` | no | defaults 15, 7, 1000, 30, true, INFO |
| `VISIT_HASH_SECRET` | no | shared by all replicas: visitor salt = HMAC(secret, UTC date); without it each process uses its own random salt (`lasteverlm-account`) |
| `RATE_LIMIT_PER_MINUTE`, `BLOCK_MINUTES`, `BAN_AFTER_STRIKES`, `STRIKE_WINDOW_HOURS`, `ACCESS_LOG_HEALTHZ_SAMPLE` | no | core's rate-limit middleware; defaults 120, 15, 3, 24, 100. The first four are only defaults: an admin overrides them at run time through `PUT /admin/settings/ratelimit` (settings key `ratelimit`, read by every service's middleware within 30 s) |
| `RETENTION_DAYS`, `BAN_MAX_DAYS` | no | days the access log, stale blocks and lifted bans are kept, and how long a ban holds at most (core's names); this service purges at every start, defaults 30, 90 |

The domain-list seed is written to the `settings` table only when the key is
missing; afterwards the admin panel owns the value. SMTP is never stored.

## Run locally

```bash
cd account
make install        # uv sync --all-extras: creates .venv with ../core installed by path, idempotent
make run-dev
```

The service depends on `lasteverlm-core` from [`core/`](../core/) of this
repository (API models, token resolution, the rate-limit middleware). It
is a path source in `pyproject.toml`, nothing is published to PyPI.

`make run-dev` serves the full API on <http://localhost:8000> with
in-memory storage and no mail server: sign-in links are printed to the
terminal, `admin@example.org` is allowed and becomes admin, and the demo
token is `demo`. This is what a frontend developer needs; nothing in it
runs in production.

```bash
curl -s -X POST localhost:8000/api/account/auth/request-link \
     -H 'content-type: application/json' -d '{"email": "admin@example.org"}'
# copy the token from the terminal, then:
curl -s 'localhost:8000/api/account/auth/callback?token=...'
curl -s localhost:8000/api/account/me -H 'authorization: Bearer demo'
```

`make run` is the production entrypoint against PostgreSQL
(`uvicorn --factory lasteverlm_account.main:create_app`). It needs the
variables above (`set -a; source .env; set +a`) and a database with core's
and this service's migrations applied.

## Test

```bash
make check          # install, then ruff check, black --check, mypy, pytest; works on a fresh checkout
```

The unit tests run against the in-memory repository and need no
database. `tests/test_postgres.py` applies the migrations to a real
PostgreSQL and checks that redeeming a voucher is atomic in SQL; it runs
when `TEST_DATABASE_URL` points at an empty, disposable database and is
skipped otherwise.

## Build and deploy

```bash
make build          # from account/: docker build -f Dockerfile -t lasteverlm-account:<git-sha> ..
```

The build context is the repository root, so that `core/` is copied into
the image next to `account/`. The image listens on
port 8000 as a non-root user. Deployment is owned by [`infra/`](../infra/):
its `make migrate` applies `account/db/migrations/*.sql` after core's
tables, its Helm chart mounts the ConfigMap and the per-concern secrets
named in the configuration table, and Kubernetes probes `GET /healthz`.

## Privacy

The visitor log (`POST /visits`, read at `GET /admin/visits`) is built so
that it cannot identify a person:

- **No IP address is stored, ever.** A visit carries `sha256(salt || ip)`
  with a salt that changes every UTC day: the same address gives the same
  hash within a day (so unique visitors per day can be counted) and an
  unrelated hash the next day. With `VISIT_HASH_SECRET` set the salt is
  `HMAC(secret, date)`, so all replicas agree on it; without it each
  process uses random bytes in memory. The salt is never written anywhere.
- **No full user agent.** Only the browser family (`chrome`, `firefox`,
  `safari`, `edge`, `bot`, ...) is kept.
- **30 days retention**, enforced by a cleanup at every service start
  (`VISIT_RETENTION_DAYS`).
- A logged-in user's id is attached to their visits, nothing else. Admins
  see visits aggregated per day and path, never single rows.

Magic-link tokens and voucher codes are stored as SHA-256 hashes only;
the plain value exists once, in the mail or in the admin's response.

**Two exceptions, for security:** the access log written by core's
rate-limit middleware (`access_log`, shown at `GET /admin/access`) holds
the raw IP address with time, path and status, and the block and ban
tables hold the addresses they act on. And `login_attempts` (shown at
`GET /admin/login-attempts`) records every request for a sign-in link
with the address, the client IP and whether it was allowed: a refused
sign-in is a security event an admin wants to attribute, so it is not
hashed like a visit; it is kept `RETENTION_DAYS` (30) like the access
log and purged at every start. Rate limiting, blocking and lifting
a ban are impossible without the address itself. These rows are visible
to admins only and are removed by this service at every start once older
than `RETENTION_DAYS` (30), with core's own purge statements; an active
ban stays until an admin lifts it, at most `BAN_MAX_DAYS` (90). The
visitor statistics above never use them.

## License

MIT, see [LICENSE](../LICENSE) at the repository root.
