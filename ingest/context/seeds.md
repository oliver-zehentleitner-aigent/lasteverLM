# Demo library

## New users get a demo library processed at the demo user's expense

**Id:** fafd2ed5-07f8-4b55-b773-67a6cf568448
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's request through the fleet lead, 2026-10-13 (one source per kind, the Zeltavia theme, the sponsor billing); seeding trigger and marker table chosen by the ingest author
**Revisit when:** sign-ups are open to the public at a volume where the sponsored processing becomes a cost worth limiting, or the demo content changes often enough to want re-seeding

Every new user's library starts with demo sources, one per kind (five
since 2026-10-14, when a recording was added at the maintainer's request:
a radio interview whose facts are in no other source, so a question
about it has to come from the transcript), written as one fictional set
so questions across sources work. Owners seeded before a source was
added do not get it: the marker means "considered once", and the demo
reset gives existing accounts the current set. They are
inserted on the owner's first library access or upload as ordinary
library sources flagged `demo`, and the worker processes them like any
upload. Their processing skips the owner's credit check and its usage
rows go to the demo user as the sponsor. Ingest marks every owner it has
considered in its own table, `library_seeds`, so seeding happens at most
once, never for an owner who already has sources and never again after
the owner deleted them.

**Reason:** a new user has no credit, so billing them would stop the
demo before it starts; the per-user library forbids sharing one set of
processed chunks between users, so every user's demo is processed once,
and someone has to pay for it. The marker lives in ingest because ingest
owns the library; a column on account's users row would make ingest
write another service's table.

**Alternatives:**
- Billing the new user, letting the balance go negative: the user's
  first sight of the product would be a debt.
- Pre-processed demo chunks shared by all users: cheapest, but the
  library is per user by design; one shared row would be visible to and
  deletable by everyone.
- `library_seeded_at` on account's users row: works, but ingest would
  write a table it does not own.
- Seeding at sign-up in account: account would have to call ingest or
  write its tables; services do not call each other.
