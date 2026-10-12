# Privacy

## Visitors are identified by a hash with a salt that lives only in memory

**Id:** 2c9f825d-7240-414c-849a-f607f0084a31
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family architecture v1 (root `docs/architecture.md`) and implementation, 2026-10-12
**Revisit when:** the visitor log is required to count unique visitors across restarts or across days

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
