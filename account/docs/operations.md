# Operations

## Configuration

All configuration comes from the environment; the service refuses to start
when a required value is missing. `.env.example` lists every variable.

| Variable | Required | Meaning |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL connection string, the shared database |
| `AUTH_JWT_SECRET` | yes | HS256 secret for session tokens, shared with ingest and rag |
| `PUBLIC_BASE_URL` | yes | base of the link in the sign-in mail |
| `DEMO_TOKEN` | no | shared demo token; unset in production |
| `ADMIN_EMAILS` | no | comma-separated admin addresses, may log in regardless of the allowlist |
| `AUTH_ALLOWED_DOMAINS` | no | seed for the allowlist in the settings table, first start only |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, `SMTP_STARTTLS` | no | the mail configuration (Secret `lasteverlm-smtp-seed`), read at start, shown read-only at `GET /admin/settings/smtp`, never stored |
| `MAGIC_LINK_TTL_MINUTES`, `JWT_TTL_DAYS`, `VOUCHER_DEFAULT_CENTS`, `VISIT_RETENTION_DAYS`, `TRUST_PROXY_HEADERS`, `LOG_LEVEL` | no | defaults 15, 7, 1000, 30, true, INFO |
| `VISIT_HASH_SECRET` | no | shared by all replicas: visitor salt = HMAC(secret, UTC date); without it each process uses its own random salt (`lasteverlm-account`) |
| `RATE_LIMIT_PER_MINUTE`, `BLOCK_MINUTES`, `BAN_AFTER_STRIKES`, `STRIKE_WINDOW_HOURS`, `ACCESS_LOG_HEALTHZ_SAMPLE` | no | core's rate-limit middleware, see `../core/docs/README.md` |

The allowlist seed is written to the `settings` table only when the key
does not exist yet; SMTP is never stored there. After that the admin panel is the source of truth; changing
the environment variable has no effect. One exception: an *empty*
persisted allowlist is re-seeded from a non-empty `AUTH_ALLOWED_DOMAINS`
at startup, because an empty list means "never configured", not an
admin's decision. The startup log states what was seeded, what was kept,
how many rows retention removed and whether the visitor salt is shared.
A `smtp` row left from the time the admin panel stored the mail
configuration is deleted at start, so the old password does not linger.

## First start on a fresh database

1. Apply `db/migrations/*.sql` in order (`make migrate` in `infra/` does this for every service; core's tables come first).
2. Start the service with `ADMIN_EMAILS` set to the first admin's address (read live, bypasses the allowlist) and `AUTH_ALLOWED_DOMAINS` as the seed. With both empty nobody can log in; the startup log warns about it. The first user who logs in becomes admin anyway; the demo user does not count.
3. Log in, open the admin panel: `GET /admin/settings/smtp` shows the mail configuration in effect, `POST /admin/settings/smtp/test` sends a test mail to the admin. Changing it means changing the Secret and restarting.

## Health

`GET /healthz` (also under `/api/account/`) runs `select 1` against the database and
answers `{"status": "ok"}`. The Kubernetes probe uses the root path.

## Behind the ingress

The service trusts the first entry of `X-Forwarded-For` for the visitor
hash and for core's rate limiter (`TRUST_PROXY_HEADERS=true`). Set it to `false` when the service is
reachable without a trusted reverse proxy in front, otherwise a caller can
choose the address that is hashed.

## Retention and cleanup

At every start the service deletes visitor-log rows older than
`VISIT_RETENTION_DAYS`, expired magic links, and — with core's own
`PURGE_SQL` statements, in one transaction — rows older than
`RETENTION_DAYS` from the tables core's rate-limit middleware writes:
`access_log` rows, `ip_blocks` rows not updated since, and `ip_bans`
rows whose ban was lifted before the cutoff, or whose ban is older than
`BAN_MAX_DAYS` (90). An active ban stays until an admin lifts it, at most
90 days. The startup log reports the counts (`retention: core tables: ...`).
The middleware itself never deletes, and no CronJob does; this service is
the only owner of that retention. There is no background scheduler, so a
pod that runs for months without a restart keeps rows longer than the
window. Restart the pod, or add a CronJob that restarts it, if that
matters.

## Local run without PostgreSQL

The unit tests use the in-memory repository. To run the HTTP API against
it for a manual look, write a small script that calls
`create_app(settings=..., repository=MemoryRepository(), mailer=...)`;
the production entrypoint `lasteverlm_account.main:app` always uses
PostgreSQL.
