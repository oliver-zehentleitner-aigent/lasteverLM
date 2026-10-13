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
