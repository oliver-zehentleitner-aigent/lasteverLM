# Core

## Core is installed from `../core` as a path source, not as a workspace member

**Id:** a4d20488-640c-433f-98d2-dabc49c45cfa
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** fleet coordination, 2026-10-12
**See:** auth.md#contractspy-mirrors-lasteverlm-core-until-core-is-published — 580d18e4-03db-4f20-9954-cb91b36ea6ca — as of 2026-10-12
**Revisit when:** core is versioned and pinned per service, or the repository adopts a root `pyproject.toml`

`pyproject.toml` lists `lasteverlm-core` like any other dependency and
resolves it with a `[tool.uv.sources]` entry pointing at `../core`
(editable). `make install` is still one `uv sync --all-extras`; the image
copies `core/` and `account/` from the repository root and installs both.
`contracts.py`, the interim mirror, is gone.

**Reason:** the family decided against a uv workspace (one root
`pyproject.toml` owned by nobody in particular) and for a plain path
install per service. The `make install` rule — `make check` works on a
fresh checkout — holds only if that one command also brings core in, so
the path is declared where `uv sync` reads it instead of in a second
install line. Nothing is published to PyPI: the three Python services
and core ship together in one repository and one release.

**Rejected alternatives:** a uv workspace at the repository root —
rejected family-wide because it adds a root build file every service
would have to agree on; `uv pip install -e ../core` as a separate
Makefile line (core's README pattern) — works, rejected here because it
bypasses `uv sync` and leaves `uv.lock` unaware of core.

## Core's rate-limit store gets tuple-row connections from the dict-row pool

**Id:** dae69130-8e13-494d-af5d-fb265e1e749d
**Type:** workaround
**Status:** superseded
**Superseded by:** none — core's scalar reads became row-factory independent (2026-10-13), the store takes the dict-row pool's connections directly and `tuple_connection` is gone
**Evidence:** confirmed
**Source:** fleet coordination, 2026-10-12
**Revisit when:** core's scalar reads are row-factory independent (announced for the next core pull request)

`PostgresRepository.tuple_connection` hands core's
`AsyncPostgresRateLimitStore` a pooled connection with the default
tuple row factory, switched for the duration of the call and switched
back afterwards. The repository itself keeps `dict_row` for its own
queries.

**Reason:** this service's pool returns dict rows (every query here reads
columns by name), while core's store reads scalars as `row[0]`, which
raises `KeyError` on a dict row. Core is fixing the reads to be
row-factory independent, but that fix is in a pull request that is not
merged yet; waiting for it would block the swap to core. Switching the
row factory on the borrowed connection is three lines, costs no second
pool and disappears without trace once core's fix lands.

**Rejected alternative:** a second, tuple-row connection pool only for
the middleware — rejected because it doubles the connection footprint of
every account pod for a temporary mismatch.

## The account service purges the tables core's middleware writes, at every start

**Id:** 7d3f0c2e-6b1a-4e5f-9c84-2a7d51e0b6f3
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** fleet coordination, 2026-10-13; ban cap confirmed by the maintainer 2026-10-13
**See:** privacy.md#retention-runs-at-service-start-not-on-a-schedule — 42e9906d-a613-4f17-896e-40484c1f125d — as of 2026-10-13
**Revisit when:** a periodic job (CronJob or in-process scheduler) exists for retention, or pods run for weeks without a restart

`AccountService.startup` runs core's three `PURGE_SQL` statements in one
transaction with core's `purge_params(RETENTION_DAYS, BAN_MAX_DAYS)`:
`access_log` rows and `ip_blocks` rows not updated since the retention
cutoff go, `ip_bans` rows go once lifted before that cutoff or once older
than `BAN_MAX_DAYS` (90). A ban holds until an admin lifts it, at most 90
days — the maintainer's decision of 2026-10-13. The counts are logged.

**Reason:** core's rate-limit middleware writes these tables on every
request and never deletes; core's `purge` helper exists but, by core's
own documentation, is run "by whoever owns the periodic job", and no one
did — on the cluster the rows grew without bound, and the README promised
30 days. Core confirmed that the account service is that owner: it is the
only service that reads the tables (admin panel), it already purges its
own visitor log at the same point, and infra plans no CronJob. The
statements are imported from `lasteverlm_core.ratelimit` rather than
copied so that the rule — which rows go, which bans stay — lives in one
place; core treats the constant as stable.

**Rejected alternatives:** an async `purge(AsyncConnection, ...)` in core —
rejected by core as a contract change for no gain over the exported
statements; a CronJob in infra — nobody planned or owns one; purging in
the middleware — core decided against it (a request handler is the wrong
place for a maintenance job).

**Known limit:** purge-at-start runs only on restarts, so a long-running
pod purges rarely; a periodic task is the follow-up (the `Revisit when`
above). The ban rule itself (until lifted, at most `BAN_MAX_DAYS`) is
core's and recorded in core's `context/ratelimit.md`; this service only
applies it.

## The rate-limit rule is written by account and read by every service through one settings row

**Id:** 3822026d-dbc7-4cda-8dd9-4422c26db004
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** fleet coordination, 2026-10-13 (maintainer wanted the rule editable in the panel)
**Revisit when:** a service other than account needs to write runtime settings, or the 30 s re-read proves too slow or too chatty

`PUT /admin/settings/ratelimit` validates the four runtime fields with
core's `RateLimitRules.parse` and stores `rules.as_json()` under core's
`RATE_LIMIT_SETTINGS_KEY` in this service's `settings` table. Core's
middleware in every service re-reads that row at most every 30 s and
falls back to its env defaults without a row or with an unusable one.
`DELETE` removes the row. `BAN_MAX_DAYS` and `RETENTION_DAYS` stay
environment-only and are shown read-only.

**Reason:** the thresholds must be the same in account, ingest and rag,
and the maintainer wants them changeable without a rollout. The one
place all three already share is the database, and the `settings` table
is account's existing admin-editable store; core defines key, shape and
bounds so that the writer and the readers cannot drift, and the bounds
live in one validator instead of being copied into this service's models.
Account owns the write because the admin panel is its API; core owns the
read because the middleware is core's.

**Rejected alternatives:** a core-owned table for runtime settings —
rejected as a second settings store for four integers; validating the
PUT with pydantic bounds in this service — rejected because core's
`parse` is what the readers trust, and two validators would need to be
kept equal; an immediate push to the other services — rejected because a
30 s delay on a threshold change is harmless and needs no signalling.

**Consequence:** `ban_max_days` and `retention_days` are not editable
here because they drive the purge at service start, not the middleware's
per-request decision; changing them is a deployment change.
