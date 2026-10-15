# Starter notebook (formerly the demo library)

## New users get a demo library processed at the demo user's expense

**Id:** fafd2ed5-07f8-4b55-b773-67a6cf568448
**Type:** decision
**Status:** superseded
**Superseded by:** 932bc8fc-0ac5-4005-929e-6c79a760f3c5
**Evidence:** confirmed
**Source:** maintainer request, 2026-10-13 (one source per kind, the Zeltavia theme, the sponsor billing); seeding trigger and marker table chosen by the ingest author
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

## New users get a copy of the starter notebook, not shared rows

**Id:** 932bc8fc-0ac5-4005-929e-6c79a760f3c5
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14 (a starter notebook the maintainer builds replaces the Zeltavia seeds; copies flagged starter, no processing, no charge); the handover to rag agreed with rag the same day
**Revisit when:** the starter grows large enough that copying its objects and chunks on first access is too slow, or users ask to receive updates of the starter after their copy

A new user gets a copy of the notebook an admin marks as the starter:
its uploads with their stored objects, rows, links and chunks with
embeddings, ready at once and flagged `starter` for the badge. Nothing
is processed and nothing is charged, since the work was done once for
the starter. The copies are the user's own, deletable like any upload.
Rag copies the outputs from the id maps ingest hands over in the same
transaction (`output_copies`). Without a starter nothing is seeded; the
Zeltavia demo seeds, their assets and the demo user's sponsorship of
their processing are gone. Owners who got the demo keep their sources
under the `starter` flag (migration 0012); nothing processes them at
the demo user's expense any more.

The copy runs where seeding ran, on the owner's first library access or
upload, not on an internal call from account: it needs no
service-to-service auth, and the seed mark it reuses already makes it
happen once. Since 2026-10-15 it also runs on the notebook list: that is
the web's first call after sign-in, and a new user saw no starter until
they opened the library.

**Alternatives:**
- Linking the maintainer's rows into the user's notebook (shared library
  rows, shared chunks): nothing is shared between users anywhere else;
  a shared row could not be deleted by the user without taking it from
  everyone, and the maintainer editing the starter would change every
  user's notebook.
- Processing the starter's files again for each user (the demo seeds'
  way): pays for the same extraction, vision, transcription and
  embeddings once per user.
- Falling back to the Zeltavia seeds without a starter: the maintainer
  wants one starter, not two kinds of demo content.


## The starter can be made again: once an hour, asking first, reusing what the user still has

**Id:** f8518e6e-678f-422c-8d8a-cec701c6aa56
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-15 (a user who deleted the starter notebook can make it again from the help page, free, once an hour, with a confirmation when one exists); reusing the user's sources and the notebook flag agreed in review the same day
**Revisit when:** users make starter copies often enough that the hourly limit or the confirmation gets in their way, or the starter changes so often that a reused source is no longer what the starter holds

`POST /starter/copy` makes a fresh copy of the current starter for the
caller, whether or not they were seeded before, and charges nothing.
Without `force`, a caller who still has a starter notebook
(`notebooks.starter`) gets 409 `starter_exists`. There is at most one
such copy an hour (`library_seeds.copied_at`; the first sign-in's copy
does not count). A starter source the caller still has, matched by its
dedupe key, is linked into the new notebook, and restored first if it is
in the trash. Only the sources that are gone are copied.

**Reason:** a user who deleted the starter notebook to tidy up has no
other way back to the guided first steps. Deleting a notebook keeps its
sources, and the library holds each content once per user, so copying
the starter's sources a second time would collide with the copies the
user still has. Linking them gives the same notebook without a
duplicate. The hourly limit bounds the storage a user can make the
service copy. The confirmation keeps a double click from making two
notebooks. Both are cheap to lift if users find them in the way.

**Alternatives:**
- A hard limit of one copy ever: a user who deleted the starter notebook
  by mistake, or deleted it again later, could never get it back. Copies
  are free and bounded by the hourly limit, so a lifetime limit protects
  nothing.
- Copying every starter source again: two library rows with one dedupe
  key, which the library's uniqueness forbids; or the user's own copies
  would have to be deleted first, losing anything they linked elsewhere.
- No confirmation, only the hourly limit: a user who still has the
  notebook gets a second one without being asked.

## Starter notebooks made before the flag are recognized by when they were made

**Id:** 5b59e266-8c9b-4ad3-ac51-298d0ce3b5b9
**Type:** workaround
**Status:** active
**Evidence:** inferred
**Source:** migration 0019 (2026-10-15); the rule is derived from how the first copy is made, not recorded anywhere
**Revisit when:** a user reports a notebook wrongly asked about ("you already have a starter notebook") or one that should have been

Migration 0019 flags a notebook as a starter copy when it links
starter-flagged sources and was created within a minute of its owner's
seed (`library_seeds.seeded_at`). The first copy is made in the same
request that writes the seed, so its notebook lands within that minute.
A notebook the owner made later and filled with starter sources does not.

**Reason:** before the flag, nothing recorded which notebook was the copy.
The heuristic only affects whether the web asks before a second copy;
a wrong answer costs one confirmation or one extra notebook, never data.
