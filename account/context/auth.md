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
