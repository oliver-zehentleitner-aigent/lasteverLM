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

Speech synthesis is priced per input character, not per token. A `tts`
row carries the character count in `tokens_in` and 0 in `tokens_out`,
and `MODEL_PRICES` lists `TTS_MODEL` with `in` in cents per million
characters (`out` 0):

```python
audio = tts.synthesize(segment)
record_usage(conn, user_id, notebook_id, "rag", "tts", tts.model, len(segment), 0, prices=prices)
```

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
   admin panel calls `lift_ban(conn, ip)`, for at most `BAN_MAX_DAYS`
   (90): the purge drops a ban older than that, lifted or not.

`AsyncPostgresRateLimitStore` takes `AsyncConnectionPool.connection`;
`MemoryRateLimitStore` is for tests and for `make run-dev` without a
database.

Retention is not the middleware's job. The account service owns it and
runs the purge at start, on its async pool, with the exported
statements:

```python
from lasteverlm_core import PURGE_SQL, RateLimitSettings, purge_params

settings = RateLimitSettings.from_env()
params = purge_params(settings.retention_days, settings.ban_max_days)
async with conn.cursor() as cur:
    for statement in PURGE_SQL:
        await cur.execute(statement, params)
```

Every statement takes the same two parameters: `cutoff` (now minus
`RETENTION_DAYS`) for `access_log`, `ip_blocks` and lifted bans, and
`ban_cutoff` (now minus `BAN_MAX_DAYS`) for bans nobody lifted. A sync
caller uses `purge(conn, retention_days, ban_max_days)`. The limiter
itself does not age bans: a ban past `BAN_MAX_DAYS` holds until the next
purge removes it.

## Providers

```python
from lasteverlm_core import OpenAICompatibleEmbedder, OpenAICompatibleLLM, make_client

client = make_client(inference)
embedder = OpenAICompatibleEmbedder(
    client, inference.embedding_model, inference.embedding_dimension
)
llm = OpenAICompatibleLLM(client, inference.llm_model, max_tokens=inference.llm_max_tokens)

result = embedder.embed(["text"])  # EmbeddingResult(vectors, usage)
answer = llm.complete(system, user, 400)  # CompletionResult(text, usage, finish_reason)
draft = llm.complete(system, user, 2000, thinking=True)
```

The embedder sends `dimensions=EMBEDDING_DIMENSION` on every call and
raises `ProviderError` when a vector of another width comes back: the
platform's embedding model is natively wider than pgvector can index,
and the OpenAI `dimensions` parameter is how it is told the width.

The language model on the platform is a reasoning model. Left alone it
spends the completion budget on thinking and returns empty content when
`max_tokens` is small, so `complete` sends the thinking switch off
unless the instance or the call says `thinking=True`; `thinking_body`
is the request fragment it adds. With thinking off, an empty answer is
a `ProviderError` (its message carries the `finish_reason`); with
thinking on, the result is returned as is and the caller reads
`finish_reason` (`"length"` means the budget ran out). `max_tokens`
falls back to the instance default, `LLM_MAX_TOKENS` (1024). Reasoning
tokens are completion tokens and are billed as such through `usage`.

Both raise `ProviderError` on a failed request. The `usage` of a result
goes straight into `record_usage`. Another provider is another module
implementing `Embedder` or `LLM`; callers are typed against the
protocols.

`OpenAICompatibleTextToSpeech(client, TTS_MODEL, voice=TTS_VOICE)`
returns the MP3 bytes of one `synthesize(text)` call. The voice
defaults to `DEFAULT_TTS_VOICE` (`ryan`): the platform's voices are not
the OpenAI names and `alloy` is rejected; it offers vivian, serena,
uncle_fu, dylan, eric, ryan, aiden, ono_anna and sohee. A failed request
is a `ProviderError`; the caller records the usage (see Accounting).

## Object storage

```python
from lasteverlm_core import S3Settings, S3Storage, object_key

storage = S3Storage(S3Settings.from_env())  # S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY
key = object_key(notebook_id, output_id, "audio.mp3")
storage.put(key, mp3, "audio/mpeg")
url = storage.presigned_get(key)  # valid PRESIGN_SECONDS (3600); expires_s= to change
storage.delete(key)
```

One bucket for the family; keys are `<notebook_id>/<source_id>/<name>`
for an upload and `<notebook_id>/<output_id>/<name>` for a file an
output produces. `get` returns the bytes, `delete(*keys)` takes one or more
keys (sent 1000 per request). A presigned GET is how a browser fetches
a private object without a bearer header; it is signed with SigV4 and
needs no request to storage. `S3_REGION` is optional (`us-east-1`).
Every failure is a `StorageError`. The client is synchronous (boto3);
an async service calls it through `anyio.to_thread.run_sync`.
`Storage` is the protocol callers are typed against; tests pass a stub
client to `S3Storage(settings, client=...)`.

## Migrations

`db/migrations/0001_core_usage.sql`, `0002_core_rate_limit.sql` and
`0003_core_usage_tts.sql` (adds `tts` to `usage.kind`) are plain SQL, one transaction each, applied by infra's `make migrate` after
infra's own migration and before account, ingest and rag. They create no
extension and reference no table of another service, because none exists
yet at that point in the order.
