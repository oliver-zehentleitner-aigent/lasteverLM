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
