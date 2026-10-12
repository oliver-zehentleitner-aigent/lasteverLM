# Core library

## The shared library is mirrored locally until it is published

**Id:** e65144ba-247d-4201-9417-18cc84e97699
**Type:** constraint
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12 (parent repository, architecture v1)
**Revisit when:** `lasteverlm-core` is published — then `contracts.py` is replaced by imports and this entry is superseded

`lasteverlm-core` will export the models (`Notebook`, `Source`,
`UsageRecord`), the token verification, the demo user id, and the
accounting helpers `record_usage` and `balance_cents`. It does not
exist yet, and this service was built the same night. Everything this
service needs from core is mirrored in `contracts.py`, written to the
signatures the architecture document gives, with no ingest-specific
logic in it, so the swap is an import change and nothing else.

**Reason:** waiting for core would have idled the service for the
duration; building the pieces into the service proper would have made
the later swap a refactoring instead of an import change.

**Known difference to expect:** the mirror's `DEFAULT_MODEL_PRICES` is
empty; core carries the family's defaults. Until the swap, a deployment
must set `MODEL_PRICES` for the embedding model (see `accounting.md`).
