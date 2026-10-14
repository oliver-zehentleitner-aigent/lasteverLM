# Privacy

## Visitors are identified by a hash with a salt that lives only in memory

**Id:** 2c9f825d-7240-414c-849a-f607f0084a31
**Type:** decision
**Status:** superseded
**Superseded by:** ab6e5d29-6800-4400-91d7-30ed0674e483
**Evidence:** confirmed
**Source:** family architecture v1 (root `docs/architecture.md`) and implementation, 2026-10-12

A visit is stored as `sha256(salt || ip)` plus the browser family, never
the address or the full user agent. The salt is 32 random bytes generated
in process memory, replaced when the UTC date changes, and never written
to the database, a file or a log (`privacy.py`).

**Reason:** the family contract asks for a visitor log that cannot
identify a person and still shows unique visitors per day. A salt that
only ever exists in memory makes the stored hash useless to anyone who
reads the database, because the one value needed to re-identify an
address is not there. Rotating it daily keeps the hash stable long
enough to count a day's unique visitors and unlinkable beyond that.

**Rejected alternatives:** storing the daily salt in the `settings`
table so hashes survive a restart — rejected because then the database
alone would let an attacker test addresses against stored hashes, which
defeats the point; deriving the salt from `AUTH_JWT_SECRET` and the date
— rejected because it reuses a secret for a second purpose and makes the
hash reproducible by anyone holding that secret; storing a truncated IP
(`/24`) — rejected because it is still personal data under GDPR and
offers no better counting. Known cost of the chosen path: after a
restart the current day's hashes change, so that day's unique-visitor
count is overstated once. Accepted.

The full user agent string is not kept for the same reason: together
with a hash it is a fingerprint. Only a coarse family (`chrome`,
`firefox`, `safari`, `edge`, `opera`, `samsung`, `bot`, `other`,
`unknown`) is stored.

## The daily visitor salt is shared across replicas through a secret, random per process without one

**Id:** ab6e5d29-6800-4400-91d7-30ed0674e483
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** first live deployment, 2026-10-12; confirmed by the maintainer 2026-10-13
**See:** privacy.md#visitors-are-identified-by-a-hash-with-a-salt-that-lives-only-in-memory — 2c9f825d-7240-414c-849a-f607f0084a31 — as of 2026-10-12
**Revisit when:** the service runs as a single replica for good, or the access log stops holding raw addresses

With `VISIT_HASH_SECRET` set, the day's salt is `HMAC(secret, UTC date)`;
without it, it is random bytes in process memory as before. Either way
the salt is never persisted, the hash still rotates daily and the stored
value stays `sha256(salt || ip)`.

**Reason:** the first deployment runs two replicas. With a per-process
random salt, one visitor hashes differently on each pod, so "unique
visitors per day" counted up to one per replica — the one number the
visitor log exists to produce was wrong in production. A secret shared by
the replicas (a Kubernetes secret, like the JWT secret) makes them agree
and also survives restarts. The privacy cost is small in the deployed
system: whoever holds the secret and the database could test addresses
against hashes, but that same operator already reads raw addresses in
core's `access_log` for 30 days. Left optional so a single-replica or
development run needs no extra secret; the startup log says which mode
is active.

**Rejected alternatives:** deriving the salt from `AUTH_JWT_SECRET` —
rejected again, one secret for one purpose; a salt row in the database —
rejected because it puts the one value needed for re-identification next
to the hashes; `replicas: 1` for account — rejected because the family
rule is that every process can run any number of times.

Pending confirmation: the maintainer was offline when this was decided
and has not yet seen the trade-off.

## Retention runs at service start, not on a schedule

**Id:** 42e9906d-a613-4f17-896e-40484c1f125d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation, 2026-10-12
**Revisit when:** the service runs for weeks without a restart, or a scheduler exists in the cluster

Rows of `visit_log` older than `VISIT_RETENTION_DAYS` (default 30) and
expired magic links are deleted in `AccountService.startup()`, once per
process start. There is no in-process timer and no CronJob.

**Reason:** a cleanup that runs at every start is one function with no
concurrency, no scheduler state and nothing to monitor, and deployments
of this service restart often enough (every image rollout) that the
window is honoured in practice. The retention promise is documented in
the README with this mechanism named, so it is not oversold.

**Rejected alternative:** a background task with `asyncio.sleep` in the
service process — rejected because with more than one replica it runs
several times, needs its own error handling and gives nothing a restart
does not. A Kubernetes CronJob was left to the infra repository to add
if the restart frequency turns out too low; `docs/operations.md` names
the condition.

## Sign-in attempts are logged with the plain client address, unlike visits

**Id:** 3b713a39-eb07-4396-8c0e-e09d9b0b852b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-13
**See:** privacy.md#visitors-are-identified-by-a-hash-with-a-salt-that-lives-only-in-memory — 2c9f825d-7240-414c-849a-f607f0084a31 — as of 2026-10-13
**Revisit when:** the retention window of core's access log changes, or the admin panel gains blocking by address so attribution needs more than a list

Every `POST /auth/request-link` writes a `login_attempts` row: time,
address as entered (lower-cased), the client IP as core's middleware
resolves it (the last `X-Forwarded-For` entry, written by the ingress) and the
outcome, `allowed` or `refused`. Admins read it at
`GET /admin/login-attempts`. Rows are deleted after `RETENTION_DAYS`
(30) at every start — the same window as core's `access_log`, not the
visitor log's own `VISIT_RETENTION_DAYS`.

**Reason:** the visitor log hashes the address because a page view is
not something anyone needs to attribute; a refused sign-in is. It is a
security event — someone outside the allowlist asked for a link — and an
admin who sees a burst of refusals wants to know whether it is one
address, one network or a partner who is simply not listed yet. A hash
with a daily salt cannot answer any of that, and the service already
keeps raw addresses for exactly this purpose in core's access log and
ban tables, with the same 30-day window. The address and the IP together
are what makes the row useful; either alone is not.

**Rejected alternative:** hashing the IP like the visitor log —
rejected because attribution is the whole point of the log, and the
daily salt rotation would even hide that two refusals on consecutive days
came from the same place. Also rejected: logging only refused attempts —
allowed ones give the admin the baseline (who signs in from where) that
makes a refusal stand out, and they are the same security purpose.

## A viewer gets e-mail addresses masked by the server

**Id:** a658f9ad-1baa-44fe-ad02-c9dea467ef71
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer order relayed by the coordinator, 2026-10-14; core's `mask_email` (#455); `masking.py`

The viewer role (read-only admin) receives every e-mail address in the
admin API masked by core's `mask_email` (`j***e@example.com`, domain in
full): users, logins, sign-in attempts, the allowlist's single addresses
(sign-in and viewer), vouchers' `created_by`, `redeemed_by` and
`sent_to`, finance costs grouped by user, the usage stats' top users, and
the starter notebook's `set_by`. Admins see full addresses. The mail
settings' sender and username stay: they are the service's own mailbox,
not a person's. A finance row of a deleted user keeps its user id.

**Reason:** a viewer needs the overview, not the identities; what the
server never sends cannot leak from a browser, a cache or a screenshot.

**Rejected alternatives:** masking in the web only — rejected because the
response would still carry the full address to every viewer's browser.
