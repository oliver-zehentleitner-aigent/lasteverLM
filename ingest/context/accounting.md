# Accounting

## An embedding model without a price refuses to start

**Id:** 4cf5c29f-cc35-4083-82a3-7f507eacfe1d
**Type:** decision
**Status:** superseded
**Superseded by:** 678d3ed9-6763-491a-b284-7f77f974d965
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12
**Revisit when:** core's default price table covers every model the inference endpoint offers, or pricing moves out of the services

If `EMBEDDING_MODEL` has no entry in the effective price table
(core defaults plus `MODEL_PRICES`), `Settings.from_env` raises and the
service does not start.

**Reason:** every model call must be accounted, and the usage row is the
only debit against a user's credit. A model billed at zero would keep
serving while silently handing out free embeddings; nobody would notice
until the provider's invoice arrived. Failing at startup names the
problem to the one person who can fix it, at the moment the
configuration is written.

**Rejected alternative:** record the usage row with `cost_cents = 0` and
log a warning. Keeps the service up through a configuration gap,
rejected because a warning in a log nobody reads is how a free tier is
born by accident. The pricing function itself still returns zero for an
unknown model, so that a usage row is never lost over a price; the
startup check is what makes that path unreachable in practice.

## Every configured model needs a price, or the service refuses to start

**Id:** 678d3ed9-6763-491a-b284-7f77f974d965
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12, extended with the summary and transcription models; core's pricing (code)
**Revisit when:** core's default price table covers every model the inference endpoint offers, or pricing moves out of the services

`Settings.from_env` calls core's `require_prices` for `EMBEDDING_MODEL`,
`LLM_MODEL` and `STT_MODEL`; one without an entry in the effective price
table (core defaults plus `MODEL_PRICES`) stops the start. Core's
`cost_cents` raises for an unpriced model as well, so no usage row is
ever written at a silent zero tariff.

**Reason:** every model call must be booked, and the usage row is the
only debit against a user's credit. A model billed at zero would serve
free calls until the provider's invoice arrived; failing at start-up
names the gap to whoever writes the configuration.

**Alternatives:**
- Booking an unpriced call at zero with a warning: keeps the service up
  through a configuration gap, and a warning nobody reads is how a free
  tier is born by accident.

## Credit is checked before each step, not reserved; a document can overdraw by a few cents

**Id:** 5bccbe95-ca18-4d02-9ca6-d9d5922a95a8
**Type:** decision
**Status:** superseded
**Superseded by:** b203f2b7-c157-4b75-834e-457f5d5d4567
**Evidence:** confirmed
**Source:** security and quality audit, 2026-10-14; accepted by the maintainer
**Revisit when:** a single source can cost more than a few cents (a more expensive model, much larger uploads), or account introduces reservations

The worker asks core's `has_credit` before a model loader's first call
and after each billed call, once before all embedding batches and once
before the summary. Nothing is reserved. So the step in flight always
completes: all embedding batches of a document, and up to four vision
calls already running in parallel, are billed even when the balance
reaches zero during them. A document can therefore overdraw its owner's
balance by a few cents.

**Reason:** a reservation needs an estimate of the cost before the work
(token counts are known only after the calls) and a hold that account
would have to honour; the amount at stake is the embedding cost of one
document or four page reads. Stopping in the middle of the embedding
batches would leave a source half indexed and its calls billed anyway.

**Alternatives:**
- A credit check before every embedding batch: the source would fail
  half embedded, with those batches still billed.
- Reserving an estimated cost up front: needs an estimator and an
  account-side hold, for a few cents.

## Adding a source is free; processing waits for credit, derived in the claim query

**Id:** 8b4d8fdd-3b1f-4f35-be45-452e15385df9
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14 (adding always allowed, processing needs credit); the derived status chosen by the ingest author from the two options the decision named
**Revisit when:** the claim query's balance subqueries show up in the database's slow log, or users need to see why exactly a source waits beyond the status

A user without credit can add sources: the upload, URL or text is stored
like any other (since 2026-10-14 as `added`, read only when it is used;
worker.md). Processing needs credit: the worker's claim query takes a
queued row only when its owner can pay (since 2026-10-15 by the start
rule within the estimated maximum, entry 1bbd3b8d-5e0b-48a1-b9be-2dccca4c4a32;
before, a positive balance; a sponsored demo seed was the exception until
the starter notebook replaced the demo seeds, 2026-10-14). The row stays
`processing` in the table; the API shows `waiting_for_credit` while it
waits. As soon as a voucher
or top-up lands in account's ledger, the next claim takes the source.
Credit running out in the middle of a job released the claim without
counting the attempt, so the source waited instead of failing; since
2026-10-15 a started read is no longer stopped for credit at all (entry
b203f2b7-c157-4b75-834e-457f5d5d4567).

**Alternatives:**
- Refusing the add with 402, the state before: the user could not even
  put a text into a notebook to look at it, and had to come back later
  to add it again.
- A stored status `waiting_for_credit` (migration for the check
  constraint) moved back to `processing` by a hook on credit changes or a
  periodic pass: the hook would need account to call ingest or ingest to
  watch account's ledger, and a pass delays every resume by its interval;
  the stored value also goes stale the moment credit arrives. Derived in
  the claim query, it is always current and needs no migration.
- Failing a source whose credit ran out mid-job: the user would have to
  find and re-add it after topping up.

## Processing one source is one billed action, keyed by the library source

**Id:** f6b1d5f7-5d21-43ae-a1c0-0e8aaa9ad0aa
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the finance redesign, maintainer decision, 2026-10-14 (actions `source:<kind>` and `demo_seed`, one `action_id` per source); the key chosen by the ingest author
**Revisit when:** a source can be processed again on purpose (re-indexing with another model), which would be a new action of its own

Every usage row ingest writes goes through core's `record_usage` with
action `source:<kind>` (`demo_seed` for the sponsored demo sources until
the starter notebook replaced them, 2026-10-14; starter copies are not
processed and book nothing) and the library source's id as `action_id`. The vision pages, the
transcription, the embeddings and the summary are one action, so the
summary is booked as `source:<kind>` too, not as a separate `summary`.
The library id is stable across retries and across a wait for credit,
so a source that took three attempts is still one action and core
books its fixed fee once.

Before every model call the worker checks that the pricing rules have an
exchange rate (credit is checked once, when the read starts; entry
1bbd3b8d-5e0b-48a1-b9be-2dccca4c4a32). Core books after the call, and
without a rate the booking fails; the call would then be paid upstream
and never booked, the worst outcome. So without a rate no worker claims a source, and a
job that finds the rate gone goes back to the queue before its next
provider call, its attempt not counted; queued sources show "pricing has
no exchange rate, ask an admin" and run once an admin sets the rate
(maintainer decision, aligned with rag). Failing the source instead, the first version, would have made
every user re-upload after the admin fixed the row. A check at start-up
alone would not do: an admin can change the row at runtime.

**Alternatives:**
- A fresh `action_id` per processing attempt: a retry after a provider
  hiccup would book the fixed fee again for the same user action.
- Booking the summary as action `summary`: splits one user action (adding
  a source) into two in the user's statement.

## A read that has started runs to the end; credit is checked once, before it starts

**Id:** b203f2b7-c157-4b75-834e-457f5d5d4567
**Type:** decision
**Status:** superseded
**Superseded by:** 1bbd3b8d-5e0b-48a1-b9be-2dccca4c4a32
**Evidence:** confirmed
**Source:** maintainer rule, 2026-10-15 ("never spend 90 % and then stop")
**Revisit when:** a single read can cost so much that a negative balance after it is more than a few cents, or account introduces reservations

The worker checks the owner's credit once, before a read starts (the
claim query takes only sources whose owner has a positive balance, and
the read checks again as it begins). Once started, the read runs to the
end and books every call, even if the balance goes below zero on the
way: a user may end slightly negative, and their next read waits until
the balance is positive again. The exchange rate is still checked before
every call, because without it a call cannot be booked at all.

**Alternatives:**
- A credit check before every model call (the previous rule): a vision
  PDF or a long recording stopped in the middle with the pages read so
  far paid for and the source not usable, the worst outcome for the
  user.
- Reserving an estimated cost up front: needs an estimator and a hold in
  account, for what is at most one read's cost.

## An action starts only if its estimated maximum is covered; then it runs to the end

**Id:** 1bbd3b8d-5e0b-48a1-b9be-2dccca4c4a32
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-15 (one rule for every service: start only within the balance, then finish)
**Revisit when:** reads overdraw by more than their estimate often enough to matter, or account introduces reservations of its own

A read starts only if the owner's balance covers its estimated maximum
plus the estimated maxima of their other funded reads still waiting;
once started it runs to the end, even below zero. Overdraw is bounded by
how far the estimate misses, not by how often a user asks.

When a process or refetch request queues a read, its estimate is stored
on the row. If the check passes, the row is marked funded at request,
and the claim takes it later whatever the balance has become, so a
confirmed agent plan never waits half-way on a source an earlier step
paid for. An unfunded row waits until the balance, less what funded
reads hold, covers its estimate. Rag applies the same rule to plans and
outputs and counts this held amount with its own. Since 2026-10-15 ingest
counts rag's waiting and processing outputs (`outputs.reserved_cents`)
as held too, so a read cannot start on balance a running output has
reserved.

**Alternatives:**
- Checking only that the balance is positive at the start (the previous
  rule, entry b203f2b7-c157-4b75-834e-457f5d5d4567): a user with one cent could queue any amount of
  work, or many requests before the first was read.
- A client-set "confirmed" flag on the request: the web and rag send the
  same bearer, so the flag could be forged and would lift every limit.
- A service proof (an HMAC header from rag): another secret path, and it
  still left the web's own requests unbounded; the start rule closes the
  gap for every caller alike.

