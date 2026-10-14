# Accounting

## An embedding model without a price refuses to start

**Id:** 4cf5c29f-cc35-4083-82a3-7f507eacfe1d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-12; maintainer review pending in the first pull request
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

## Credit is checked before each step, not reserved; a document can overdraw by a few cents

**Id:** 5bccbe95-ca18-4d02-9ca6-d9d5922a95a8
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** security and quality audit, 2026-10-14; accepted by the maintainer through the coordinating agent
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
**Source:** the maintainer's decision through the coordinating agent, 2026-10-14 (adding always allowed, processing needs credit); the derived status chosen by the ingest author from the two options the decision named
**Revisit when:** the claim query's balance subqueries show up in the database's slow log, or users need to see why exactly a source waits beyond the status

A user without credit can add sources: the upload, URL or text is stored
and queued like any other. Processing needs credit, so the worker's claim
query only takes a row whose owner has a positive balance (or a sponsored
demo seed). The row stays `processing` in the table; the API shows
`waiting_for_credit` when the owner has no credit. As soon as a voucher
or top-up lands in account's ledger, the next claim takes the source.
Credit running out in the middle of a job releases the claim without
counting the attempt, so the source waits instead of failing.

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

