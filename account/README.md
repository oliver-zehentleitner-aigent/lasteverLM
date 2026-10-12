# account

[![ci](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ci.yml)
[![ktw-lint](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml/badge.svg)](https://github.com/oliver-zehentleitner/lasteverLM/actions/workflows/ktw-lint.yml)
[![Keep the Why](https://keepthewhy.com/assets/badge.svg)](https://keepthewhy.com)

The account service of [lasteverLM](../README.md), a NotebookLM-style
assistant, in the `account/` directory of the one repository. It owns who may use the system and what they
may spend: passwordless magic-link login restricted to allowed e-mail
domains, session tokens the other services verify, prepaid credits via
single-use vouchers, the admin panel backend (SMTP and domain settings,
users, logins, vouchers) and a visitor log that stores no personal data.

The API contract this service implements is
[`docs/architecture.md`](../docs/architecture.md) at the repository root,
prefix `/api/account`. Changes to the contract are made there first.

- How to operate it: [`docs/operations.md`](docs/operations.md)
- Why it is built this way: [`context/index.md`](context/index.md)

## API, prefix `/api/account`

| Area | Endpoints |
|---|---|
| Login | `POST /auth/request-link` (always 202), `GET /auth/callback?token=` → `{jwt, user}` |
| Account | `GET /me`, `POST /vouchers/redeem` → `User`, `POST /visits` (204, works without a token) |
| Admin | `GET /admin/users`, `GET /admin/logins?limit=`, `GET /admin/visits?days=`, `GET/PUT /admin/settings/smtp`, `POST /admin/settings/smtp/test`, `GET/PUT /admin/settings/domains`, `POST /admin/vouchers` |
| Access control | `GET /admin/blocks`, `GET /admin/bans?include_lifted=`, `DELETE /admin/bans/{ip}`, `GET /admin/access?limit=` |
| Health | `GET /healthz`, also at the server root for the Kubernetes probe |

Errors are `{"error": "<message>"}`: 401 unauthenticated, 403 not
admin, 404 unknown or used voucher or no active ban, 409 SMTP not
configured, 422 bad request, 502 mail could not be sent.

Rate limiting and blocking themselves happen in a middleware from
`lasteverLM-core` that runs in every service: too many requests from one
address give 429 and a 15-minute block, the third block within 24 hours a
ban. This service only shows the result to admins (`/admin/blocks`,
`/admin/bans`, `/admin/access`) and lets them lift a ban.

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
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, `SMTP_STARTTLS` | no | seed for the SMTP settings, first start only (`lasteverlm-smtp-seed`) |
| `MAGIC_LINK_TTL_MINUTES`, `JWT_TTL_DAYS`, `VOUCHER_DEFAULT_CENTS`, `VISIT_RETENTION_DAYS`, `TRUST_PROXY_HEADERS`, `LOG_LEVEL` | no | defaults 15, 7, 1000, 30, true, INFO |

Seeds are written to the `settings` table only when the key is missing;
afterwards the admin panel owns the value.

## Run locally

```bash
cd account
make install        # uv sync --all-extras: creates .venv, idempotent
make run-dev
```

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

`make run` is the production entrypoint against PostgreSQL. It needs the
variables above (`set -a; source .env; set +a`) and a database with the
migrations applied.

## Test

```bash
make check          # install, then ruff, mypy, pytest; works on a fresh checkout
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

The build context is the repository root, so that `core/` can be copied
into the image once the service depends on it. The image listens on
port 8000 as a non-root user. Deployment is owned by [`infra/`](../infra/):
its `make migrate` applies `account/db/migrations/*.sql` after core's
tables, its Helm chart mounts the ConfigMap and the per-concern secrets
named in the configuration table, and Kubernetes probes `GET /healthz`.

## Privacy

The visitor log (`POST /visits`, read at `GET /admin/visits`) is built so
that it cannot identify a person:

- **No IP address is stored, ever.** A visit carries `sha256(salt || ip)`,
  where the salt is random, lives only in process memory and is replaced
  every UTC day. The same address gives the same hash within a day (so
  unique visitors per day can be counted) and an unrelated hash the next
  day. The salt is never written anywhere; a restart simply starts a new
  one.
- **No full user agent.** Only the browser family (`chrome`, `firefox`,
  `safari`, `edge`, `bot`, ...) is kept.
- **30 days retention**, enforced by a cleanup at every service start
  (`VISIT_RETENTION_DAYS`).
- A logged-in user's id is attached to their visits, nothing else. Admins
  see visits aggregated per day and path, never single rows.

Magic-link tokens and voucher codes are stored as SHA-256 hashes only;
the plain value exists once, in the mail or in the admin's response.

**One exception, for security:** the access log written by core's
rate-limit middleware (`access_log`, shown at `GET /admin/access`) holds
the raw IP address with time, path and status, and the block and ban
tables hold the addresses they act on. Rate limiting, blocking and lifting
a ban are impossible without the address itself. These rows are kept for
30 days and are visible to admins only. The visitor statistics above
never use them.

Status: in development. Nothing is deployed yet.

## License

MIT, see [LICENSE](../LICENSE) at the repository root.
