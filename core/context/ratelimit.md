# Rate limiting

## The sliding window is a count over access_log

**Id:** b92de8a5-cdbc-4e7a-958f-c9b461e2c554
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** core design, 2026-10-12; parent docs/architecture.md, "Rate limiting"
**Revisit when:** request volume makes the per-request count query visible in the database, or a shared cache enters the platform

The per-minute limit is `count(*)` over `access_log` for the client IP
in the last sixty seconds, excluding rows with status 429. `ip_blocks`
holds only the block end, the strike count and the time of the last
strike.

**Reason:** every request writes an `access_log` row anyway, so the
window exists without a second data structure, is exact rather than a
bucket approximation, and is shared by all replicas of all services
because it lives in the one database. Excluding 429s matters: while a
client is blocked its rejected requests are still logged, and if they
counted, a client that kept retrying would be over the limit again the
moment the block ended, turning one block into a permanent one.

**Rejected alternative:** a request counter and window start in
`ip_blocks`. Fewer rows scanned, rejected because a fixed window lets a
client send twice the limit across a window edge and because the
counter must be reset by someone.

**Rejected alternative:** in-memory counters per pod. Fastest, rejected
because the API services run with at least two replicas behind one
ingress and a limit per pod is a limit multiplied by the replica count.

## Plain ASGI middleware, not a Starlette base class

**Id:** b36407f7-b2e7-4f00-9209-0e7c49150934
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** core design, 2026-10-12
**Revisit when:** the middleware needs to read or rewrite the request body

`RateLimitMiddleware` implements the ASGI callable directly and wraps
`send` to learn the response status. It depends on `anyio` for running
the sync store in a worker thread, not on Starlette or FastAPI.

**Reason:** the middleware has to run the blocking PostgreSQL driver
without stalling the event loop and has to see the final status code of
every response, including streamed ones; the plain protocol gives both
with a few lines. Keeping web frameworks out of core means the library
installs into a worker process that has no HTTP server at all.

**Rejected alternative:** Starlette's `BaseHTTPMiddleware`. Shorter to
write, rejected because it buffers responses, has known interactions
with streaming and background tasks, and would make FastAPI a
dependency of a library two of whose users are workers.

## X-Forwarded-For is trusted by default

**Id:** 77cf17e5-23d0-4679-87dc-080107344514
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** parent docs/architecture.md ("as set by the ingress, never trusted from anywhere else"); core design 2026-10-12
**Revisit when:** a service becomes reachable other than through the ingress, or the ingress is replaced

`client_ip` takes the first `X-Forwarded-For` entry when
`trust_forwarded` is true (the default) and the peer address otherwise.
A value that is not an IP address becomes `0.0.0.0`.

**Reason:** in the cluster the pods are reachable only through
ingress-nginx, which sets the header from the real peer, so trusting it
there is the only way to see the client at all; the peer address would be
the ingress on every request. The default is the cluster case because
that is production; a local run passes `trust_forwarded=False`. The
fallback to a fixed unknown address keeps a malformed header from
breaking the request or the `inet` column, at the cost of lumping all
such clients together, which is acceptable because only a client that
bypassed the ingress could send one.

## An active ban survives the thirty-day purge

**Id:** 51544138-d1a5-41df-aaae-30101ed4315b
**Type:** decision
**Status:** superseded
**Superseded by:** a9ede8b5-5da7-4907-825a-0f7cb6d3b693
**Evidence:** inferred
**Source:** parent docs/architecture.md, "Rate limiting" (two sentences that pull apart: a ban holds until an admin lifts it, and raw IPs are purged after thirty days); core design 2026-10-12
**Revisit when:** the maintainer confirms or changes the retention rule for bans (written while the maintainer was unavailable; the first attended session confirms it)

`purge` deletes `access_log` and `ip_blocks` rows older than the
retention period, but from `ip_bans` only rows whose ban was lifted
before the cutoff. A ban nobody lifted stays, and so does its IP.

**Reason:** the architecture says both that a banned IP is refused until
an admin lifts the ban and that raw IPs are purged after thirty days. The
two cannot both hold for an active ban older than thirty days; read
literally, the purge would quietly end every ban after a month without
any admin seeing it. The security purpose that justifies keeping the IP
is strongest for exactly these rows, so the ban wins. This is the
author's reading, not a confirmed instruction.

**Rejected alternative:** purge bans by age like the other tables.
Rejected because it turns "until lifted" into "for thirty days" without
telling the admin panel.

## An active ban survives the purge for at most ninety days

**Id:** a9ede8b5-5da7-4907-825a-0f7cb6d3b693
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's decision on the ban retention rule, 2026-10-13
**Revisit when:** bans need to outlive ninety days (repeat offenders)

A ban holds until an admin lifts it, but at most `BAN_MAX_DAYS` (default
90). The limiter enforces the cap itself: `is_banned(ip, since)` counts
only an unlifted ban created at or after `now - BAN_MAX_DAYS`, so an
older ban stops refusing requests at the exact moment it expires. The
purge is cleanup, not the rule: `PURGE_SQL` drops from `ip_bans` every
row lifted before the retention cutoff (`RETENTION_DAYS`, 30, like
`access_log` and `ip_blocks`) and every row created before
`ban_cutoff`, lifted or not. Both cutoffs come from `purge_params`, so
the account service, which runs the statements at start on its async
pool, passes one dict. Until that purge runs, the admin panel's list may
still show an expired ban.

**Reason:** the architecture's two rules pulled apart for an active ban
older than the retention period: "until an admin lifts it" would keep a
raw IP forever, "purged after thirty days" would end every ban after a
month without anyone deciding it. The maintainer settled it with an upper
bound: long enough that a ban outlasts any burst and an admin has time to
look, short enough that no raw IP is kept indefinitely.

**Rejected alternative:** an active ban is never purged (the earlier,
unconfirmed reading). Rejected by the maintainer: it keeps personal data
without a time limit.

**Rejected alternative:** bans purged at `RETENTION_DAYS` like the other
tables. Rejected: thirty days ends a ban too soon for a security measure.

**Rejected alternative:** the purge alone ends a ban. Rejected because
the purge runs when the account service starts, so a ban would outlive
its ninety days by however long the service had been running.

## The four thresholds are runtime settings, re-read every thirty seconds

**Id:** 39da528f-5128-45cb-9393-41240be9cac4
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's request to see and edit the ban and block rules in the admin panel, 2026-10-13; design relayed by the coordinating agent
**Revisit when:** a threshold must apply faster than thirty seconds, or the settings read shows up in request latency

`per_minute`, `block_minutes`, `ban_after_strikes` and
`strike_window_hours` come from account's `settings` table, key
`ratelimit`, a jsonb object with exactly those four integer fields within
`RATE_LIMIT_RULE_BOUNDS`. The env values stay the defaults. Each limiter
re-reads the row through the store it already has at most every thirty
seconds. A missing row means the defaults; an unusable row or an
unreadable table means the defaults plus one warning per distinct
problem. `RateLimitRules.parse` is the one validation, used by the
limiter on read and by account's PUT on write. `BAN_MAX_DAYS` and
`RETENTION_DAYS` stay env only: they govern the purge, not the rule.

**Reason:** an operator has to be able to tighten or loosen a threshold
during an incident without a deploy. One row in the database is seen by
every replica of every service, the same place the blocks and bans
already live, so the rule and its state cannot drift apart between
pods. Thirty seconds bounds the extra read to two per minute per process
and still applies a change within the minute an admin expects.

**Rejected alternative:** env only, a redeploy to change a threshold.
Rejected by the maintainer: too slow and too heavy for an incident.

**Rejected alternative:** a per-service cache longer than thirty
seconds. Rejected because an admin who saves a threshold expects it in
force within a minute everywhere.

**Rejected alternative:** a missing row also warns. Not done: no row is
the normal state until an admin first saves the rules, and a warning
every process start would teach operators to ignore the warning that
matters, the malformed row.
