# Database access

## No database driver in core: structural connection types, sync and async

**Id:** fbe7da09-b351-4102-981f-ee4d2f5593c4
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** core design and family coordination, 2026-10-12 (account runs an async pool, ingest and rag sync ones)
**Revisit when:** the services converge on one of sync and async, or core needs a connection of its own

`record_usage`, `balance_cents` and the rate-limit stores take the
caller's psycopg 3 connection and type it as a small `Protocol` (a
`cursor()` context manager with `execute` and `fetchone`). Each helper
exists twice, sync and `a`-prefixed async, over the same SQL, which is
also exported as constants. Core opens no connection and owns no pool.

**Reason:** the account service runs on an async pool, ingest and rag on
sync ones; a helper that fits one of them does not fit the other, and
two thin wrappers over one statement are cheaper than making a service
change its driver model. Structural typing keeps psycopg out of core's
dependencies, so the tests run against a fake connection with no
database and the library installs anywhere the services do. Exporting
the SQL lets account embed the balance in an admin report without a
second definition of it.

**Rejected alternative:** depend on psycopg and type the connections
nominally. More precise types, rejected because it ties the library to
one driver for two functions and makes every test need the real
connection class.

**Rejected alternative:** core owns the pool and the services ask it for
connections. Rejected because each service already has its pool and its
transaction boundaries; a second pool would double connections on the
managed database and blur who commits.

## usage has no foreign keys

**Id:** 405223bd-dc1e-4452-8791-0f9ee504da3b
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** parent docs/architecture.md, migration order infra, core, account, ingest, rag; core design 2026-10-12
**Revisit when:** the migration order changes, or a deletion must cascade into usage

`usage.user_id` and `usage.notebook_id` reference nothing. Core's
migration runs before account creates `users` and before ingest creates
`notebooks`, so a constraint could not be declared there; and a deleted
notebook must keep what it cost, because the balance is computed from
these rows. The admin panel joins by id and tolerates a missing notebook.

## SQL is tested against a throwaway container, with a two-column ledger

**Id:** 4c59c136-5bfc-4fcf-8109-754aa714c53d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12 (maintainer: cover the SQL paths against a real PostgreSQL once Docker is on the machine); core design
**Revisit when:** infra's local compose stack exists and the family's tests run against it, or account's ledger changes shape

`make test-postgres` starts a `pgvector/pgvector` container, applies
core's own migrations to the empty database and runs the SQL paths
(usage accounting, the rate-limit stores, purge, lift) against it, with
tuple-row and dict-row connections, sync and async. The `ledger` table
that the balance query reads belongs to the account service; the test
creates it as the two columns the query uses. The target is not part of
`make check` and exits cleanly without Docker.

**Reason:** the unit tests prove the helpers send the right statement
to a fake; they cannot prove the statement is valid SQL, that `inet`
and `uuid` parameters bind, or that a dict-row connection gets its
value back. The first run of this suite found exactly such a defect
that the fakes had passed. Keeping it out of `make check` keeps CI's
Python job free of a Docker socket; keeping the ledger to two columns
keeps core's tests from depending on another service's migration files,
which would make account's schema a build input of core.

**Rejected alternative:** apply account's migration in the test.
Rejected because the dependency points the wrong way: account depends
on core, and core's tests would break on account's unrelated changes.

**Rejected alternative:** run the SQL tests in `make check` and skip
them automatically without a database. Rejected because a silently
skipped integration test looks green for the wrong reason; an explicit
target says what it needs.
