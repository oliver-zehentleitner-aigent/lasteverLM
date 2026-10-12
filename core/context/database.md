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
