# Rate limiting

## The sliding window is a count over access_log

**Id:** 
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

**Id:** 
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

**Id:** 
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

**Id:** 
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** parent docs/architecture.md, "Rate limiting" (two sentences that pull apart: a ban holds until an admin lifts it, and raw IPs are purged after thirty days); core design 2026-10-12
**Revisit when:** the maintainer confirms or changes the retention rule for bans

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
