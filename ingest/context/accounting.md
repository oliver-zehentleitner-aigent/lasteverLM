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
