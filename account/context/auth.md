# Authentication

## `contracts.py` mirrors lasteverLM-core until core is published

**Id:** 580d18e4-03db-4f20-9954-cb91b36ea6ca
**Type:** workaround
**Status:** superseded
**Superseded by:** a4d20488-640c-433f-98d2-dabc49c45cfa
**Evidence:** confirmed
**Source:** fleet coordination, 2026-10-12

The shared pieces this service needs from `lasteverLM-core` — the `User`
model, JWT issue and verify, the demo-token resolution and the demo user
id — are mirrored in `contracts.py`, because core is being written in
parallel and did not exist when this service was started. The module is
written so that it becomes a thin re-export once core lands; nothing
else in the service imports `jwt` or knows the claim layout.

Resolved the same day: core landed in `core/` of this repository and is
installed by path (`core.md`); the mirror was deleted rather than kept
as a re-export, because a module that only re-exports invites drift.

**Reason:** the services are built at the same time by separate sessions
and may not block on each other. The mirror is the smallest thing that
lets this service be tested end to end now. The cost is a second copy of
the token logic that must match core's byte for byte; the token format
(HS256, `sub` = user id, issuer `lasteverlm`, 7 days) is fixed in the
family's `docs/architecture.md`, which is what both copies implement.

## Addresses in `ADMIN_EMAILS` bypass the domain allowlist; an empty allowlist denies everyone else

**Id:** 5bef96eb-4ba1-498e-b26f-ca77f8a56fff
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation, 2026-10-12

`is_allowed()` accepts an address when its domain is in the
`allowed_domains` setting *or* when the address itself is listed in
`ADMIN_EMAILS`. With no domains configured and no admin addresses,
nobody can request a link.

**Reason:** the allowlist lives in the database and is edited through the
admin panel, so on a fresh deployment there is a bootstrapping gap: the
first admin cannot log in to set the domains that would let them log in.
`AUTH_ALLOWED_DOMAINS` seeds the list once, but an operator who forgot
it would be locked out with no way in short of SQL. Letting the admin
addresses through closes that gap with a value the operator already has
to set. An empty list failing closed rather than open is the only safe
default for a service whose whole purpose is to restrict who gets in.

**Rejected alternative:** treating an empty allowlist as "allow all" so
the first login always works — rejected because a configuration mistake
would silently turn the deployment public, and the project's stance is
to fail loudly rather than serve on.

## E-mail addresses are validated for shape only, not deliverability

**Id:** 29549d0f-a478-4bfe-b909-6270ee999e00
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation, 2026-10-12

Request bodies accept any string of the form `local@domain` without
whitespace (`models.Email`); pydantic's `EmailStr` with the
`email-validator` package is not used.

**Reason:** `email-validator` rejects reserved and special-use names
such as `.test`, `.invalid` and `localhost`. The family contract seeds
the demo user as `demo@localhost`, and the test suite uses reserved
domains on purpose so no real address can ever receive a test mail; both
would be refused. Whether an address can receive mail is decided by the
SMTP server when the link is sent, and the allowlist decides whether it
may log in — a stricter syntax check in between adds a dependency and
removes nothing an attacker could use.

**Rejected alternative:** `EmailStr` with the `email-validator`
dependency — the obvious choice, rejected for the reasons above after it
broke the first test run.

## The demo user is seeded by migration, never counts as the first user and can never be admin

**Id:** 21f1e426-85c5-4569-b99e-1c73c84d7005
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family architecture v1 (root `docs/architecture.md`) and implementation, 2026-10-12

Migration `0001` inserts the demo user (`00000000-0000-4000-8000-000000000001`,
`demo@localhost`) and `0002` credits it once. The rule "the first user
ever created becomes admin" ignores that row, and `require_admin()`
refuses the demo id even if `is_admin` were set in the database.

**Reason:** the family contract has every service resolve `DEMO_TOKEN`
to this id, so the row has to exist before anyone logs in — a migration
is the one place that runs before every service. Because it exists
first, a naive "no users yet → admin" check would never fire for the
real first login; the subquery excludes the demo id. And the demo token
is a shared secret meant for recordings and development, so whoever
holds it must not be able to reach the admin panel, whatever the row
says.

**Rejected alternative:** creating the demo user lazily on first use of
the demo token — rejected because ingest and rag resolve the token too
and would write `usage` rows for a user that account has not created
yet, breaking the balance join.
