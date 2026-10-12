# Storage

## One repository interface, PostgreSQL in deployment, in-memory in tests

**Id:** a956dbc8-6b95-482a-a50b-f5725bb3178d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation, 2026-10-12
**Revisit when:** a second service needs the same tables through Python, or the SQL grows past what plain strings can carry

All database access goes through the `Repository` protocol
(`repository.py`) with two implementations: `PostgresRepository` on
psycopg 3 with hand-written SQL, and `MemoryRepository` for the unit
tests and for running the API without a database. Every operation that
has to be atomic — consuming a magic link, redeeming a voucher, creating
the first user — is one repository call, so the service layer never
opens a transaction.

**Reason:** the family rule is "every stage is an interface with one
implementation"; here the second implementation pays for itself at once,
because the whole service logic (login flow, allowlist, admin gate,
voucher single-use, balance arithmetic, visitor hashing) is tested in
well under a second with no PostgreSQL on the machine. Keeping atomicity
inside the repository means the memory implementation can use one lock
and the PostgreSQL one a conditional `update ... returning` inside a
transaction, and the service does not have to know which it is talking
to.

**Rejected alternatives:** SQLAlchemy with an ORM and SQLite for tests —
rejected because the SQL this service needs (`on conflict`, a
`not exists` subquery inside an insert, `jsonb`) is PostgreSQL-shaped
and would either be dumbed down for SQLite or tested against a different
dialect than the one in production; testing only against a real
PostgreSQL — rejected because it would make every test run depend on a
service none of the agent sessions has locally. Known cost: the
PostgreSQL implementation's own correctness is covered only by
`tests/test_postgres.py`, which runs when `TEST_DATABASE_URL` is set and
is otherwise skipped, so a CI job with a PostgreSQL service container is
the missing piece.
