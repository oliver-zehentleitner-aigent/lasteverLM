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
