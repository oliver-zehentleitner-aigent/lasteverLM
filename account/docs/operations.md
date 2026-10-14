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
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, `SMTP_STARTTLS` | no | the mail configuration (Secret `lasteverlm-smtp`), read at start, shown read-only at `GET /admin/settings/smtp`, never stored |
| `MAGIC_LINK_TTL_MINUTES`, `LINK_QUOTA_PER_HOUR`, `JWT_TTL_DAYS`, `VOUCHER_DEFAULT_CENTS`, `VISIT_RETENTION_DAYS`, `TRUST_PROXY_HEADERS`, `LOG_LEVEL` | no | defaults 15, 5 (sign-in links per address per hour), 1 (a session token lives a day; sign-out is client-side), 1000, 30, true, INFO |
| `VOUCHER_KEY` | yes | 32 bytes base64; voucher codes at rest are encrypted under it. Generate once, keep stable: a changed key leaves every stored code unrecoverable (vouchers stay redeemable) |
| `VISIT_HASH_SECRET` | no | shared by all replicas: visitor salt = HMAC(secret, UTC date); without it each process uses its own random salt (`lasteverlm-account`) |
| `RATE_LIMIT_PER_MINUTE`, `BLOCK_MINUTES`, `BAN_AFTER_STRIKES`, `STRIKE_WINDOW_HOURS`, `ACCESS_LOG_HEALTHZ_SAMPLE` | no | core's rate-limit middleware, see `../core/docs/README.md`; the first four are defaults the admin panel overrides at run time (`settings` key `ratelimit`, picked up by every service within 30 s; `DELETE /admin/settings/ratelimit` returns to these values) |

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
2. Start the service with `ADMIN_EMAILS` set to the first admin's address (read live, bypasses the allowlist) and `AUTH_ALLOWED_DOMAINS` as the seed of the domain list. With both empty and no single addresses listed nobody can log in; the startup log warns about it. Single addresses are added in the admin panel, there is no seed for them. The first user who logs in becomes admin anyway; the demo user does not count.
3. Log in, open the admin panel: `GET /admin/settings/smtp` shows the mail configuration in effect, `POST /admin/settings/smtp/test` sends a test mail to the admin. Changing it means changing the Secret and restarting.

## System page

`GET /admin/system` reads pods and deployments of the namespace through the
Kubernetes API with the pod's ServiceAccount. The chart gives the account
Deployment a ServiceAccount with a Role for `get` and `list` on `pods` and
`apps/deployments`; without it the API answers 403, the service logs one
warning per request and returns the page with empty lists. `APP_VERSION` and
`APP_COMMIT` come from the ConfigMap and are shown on `/healthz` as well.

## Health

`GET /healthz` (also under `/api/account/`) answers `{"status": "ok", "version",
"commit", "dependencies": {"postgres": "ok"|"down"}}`. The dependency state is core's
probe: `select 1` with a 2-second timeout, cached for 15 seconds; a failing database
reads `"down"` while the status stays `"ok"`, so the Kubernetes probe keeps the pod
(it answers) and the System page shows what is wrong. The Kubernetes probe uses the
root path.

## Behind the ingress

The service trusts the last entry of `X-Forwarded-For` (the ingress's) for the visitor
hash and for core's rate limiter (`TRUST_PROXY_HEADERS=true`). Set it to `false` when the service is
reachable without a trusted reverse proxy in front, otherwise a caller can
choose the address that is hashed.

## Retention and cleanup

At every start the service deletes visitor-log rows older than
`VISIT_RETENTION_DAYS`, expired magic links, `login_attempts` rows older
than `RETENTION_DAYS`, and — with core's own
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
