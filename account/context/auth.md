# Authentication

## `contracts.py` mirrors lasteverLM-core until core is published

**Id:** 580d18e4-03db-4f20-9954-cb91b36ea6ca
**Type:** workaround
**Status:** active
**Evidence:** confirmed
**Source:** fleet coordination, 2026-10-12
**Revisit when:** `lasteverlm-core` is installable from the family's index or Git

The shared pieces this service needs from `lasteverLM-core` — the `User`
model, JWT issue and verify, the demo-token resolution and the demo user
id — are mirrored in `contracts.py`, because core is being written in
parallel and did not exist when this service was started. The module is
written so that it becomes a thin re-export once core lands; nothing
else in the service imports `jwt` or knows the claim layout.

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
