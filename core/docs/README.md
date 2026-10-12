# Using lasteverlm-core from a service

The README covers installation. This page is the longer form of how the
pieces fit into a FastAPI service.

## Startup

```python
from lasteverlm_core import (
    AuthSettings,
    ConfigError,
    InferenceSettings,
    load_model_prices,
    require_prices,
)

try:
    auth = AuthSettings.from_env()
    inference = InferenceSettings.from_env()
    prices = load_model_prices()
    require_prices(prices, [inference.llm_model, inference.embedding_model])
except ConfigError as exc:
    raise SystemExit(f"configuration: {exc}") from exc
```

Every loader takes an optional `env` mapping, which is how tests pass
their own environment instead of patching `os.environ`.

## Authentication

```python
from fastapi import Depends, Header, HTTPException
from lasteverlm_core import AuthError, Principal, current_user


def principal(authorization: str | None = Header(default=None)) -> Principal:
    try:
        return current_user(authorization, auth)
    except AuthError as exc:
        raise HTTPException(401, {"error": str(exc)}) from exc
```

`Principal.scheme` is `"jwt"` or `"demo"`; a handler that must not be
reachable with the shared demo token (an admin action) checks it.

The account service issues tokens with `issue_jwt(user_id, secret)`;
the other services only verify. Both schemes may be configured at once,
so a development deployment can log in by mail and still run a recorded
demo with the token.

## Accounting

Before a model call: `balance_cents(conn, user_id) > 0`, otherwise 402
`{"error": "credit exhausted"}`. After it: `record_usage(...)` with the
`Usage` the provider returned. `record_usage` prices the row and raises
`UnpricedModelError` before touching the database when the model has no
price; `require_prices` at startup makes that unreachable in a correctly
configured deployment. The caller owns the transaction. The account
service, which runs on an async pool, uses `abalance_cents` and
`arecord_usage`; `BALANCE_SQL` and `USAGE_SQL` are exported for a report
query that needs them inline.

## Rate limiting

```python
from lasteverlm_core import (
    PostgresRateLimitStore,
    RateLimiter,
    RateLimitMiddleware,
    RateLimitSettings,
)

limiter = RateLimiter(PostgresRateLimitStore(pool.connection), RateLimitSettings.from_env())
app.add_middleware(RateLimitMiddleware, limiter=limiter, service="rag", auth=auth)
```

The middleware is pure ASGI and goes outermost. Per request it asks the
limiter for a decision (403 banned, 429 blocked with `Retry-After`, or
pass), lets the app answer, and writes one `access_log` row with the
response status and the user the bearer token resolved to (anonymous
when it did not). Requests to a path ending in `/healthz` are logged one
in `ACCESS_LOG_HEALTHZ_SAMPLE`.

Rules, all per client IP (`X-Forwarded-For` from the ingress, else the
peer address):

1. More than `RATE_LIMIT_PER_MINUTE` logged requests in the last minute
   (the limiter's own 429s not counted): 429 for `BLOCK_MINUTES`, one strike.
2. Strikes accumulate while each new one is within `STRIKE_WINDOW_HOURS`
   of the previous; after a quiet window the count restarts at one.
3. The `BAN_AFTER_STRIKES`th strike bans: 403 on everything until the
   admin panel calls `lift_ban(conn, ip)`.

`AsyncPostgresRateLimitStore` takes `AsyncConnectionPool.connection`;
`MemoryRateLimitStore` is for tests and for `make run-dev` without a
database. `purge(conn, RETENTION_DAYS)` deletes expired rows from the
three tables; it is run by whoever owns the periodic job (infra's
CronJob or the account service), not by the middleware.

## Providers

```python
from lasteverlm_core import OpenAICompatibleEmbedder, OpenAICompatibleLLM, make_client

client = make_client(inference)
embedder = OpenAICompatibleEmbedder(
    client, inference.embedding_model, inference.embedding_dimension
)
llm = OpenAICompatibleLLM(client, inference.llm_model)

result = embedder.embed(["text"])  # EmbeddingResult(vectors, usage)
answer = llm.complete(system, user, 400)  # CompletionResult(text, usage)
```

Both raise `ProviderError` on a failed request, a vector of the wrong
dimension or an empty answer. The `usage` of a result goes straight into
`record_usage`. Another provider is another module implementing
`Embedder` or `LLM`; callers are typed against the protocols.

## Migrations

`db/migrations/0001_core_usage.sql` and `0002_core_rate_limit.sql` are
plain SQL, one transaction each, applied by infra's `make migrate` after
infra's own migration and before account, ingest and rag. They create no
extension and reference no table of another service, because none exists
yet at that point in the order.
