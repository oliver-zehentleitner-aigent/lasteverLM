# Credit

## Credit is checked before the first provider call; usage rows are the debit

**Id:** 77df75c3-cd3c-45bb-8250-6e8968e3e488
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** family coordination, 2026-10-12; implementation session, 2026-10-12; re-checked against the code in the audit of 2026-10-14
**Revisit when:** pricing moves out of the writer, or a provider call is made before the credit check

The ask flow reads the caller's balance before embedding the question and
answers 402 when it is zero, so a user without credit causes no provider
call and no usage row. The balance is the sum of the `ledger` credits
minus the sum of `usage.cost_cents`; every embedding and LLM call writes
one `usage` row priced at write time from the `MODEL_PRICES` table in the
configuration. There is no second ledger write: the usage row is the debit.
A configured model without a price stops the service at startup.

**Reason:** the credit rule is family-wide and the check belongs before
any spend. Pricing at write time by the writer keeps accounting a single
insert per call; refusing to start without a price (family rule) means a
pricing gap can never produce free calls.

**Rejected alternative:** a separate ledger debit per call written by the
account service from the usage rows. Rejected by the family because it
doubles the writes and leaves a window in which usage exists but is not
yet charged.

**Since the core library shipped:** the balance check is core's
`has_credit` and the priced insert core's `record_usage`, called from
`store.py` with the `MODEL_PRICES` table; the rule above is unchanged.
The earlier mirrors in this service are gone (see `contracts.md`).
