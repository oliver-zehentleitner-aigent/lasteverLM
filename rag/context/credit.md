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

**Since the finance redesign (2026-10-14):** core's `record_usage` fixes a
cost and a charge per row (account's pricing rules), and the balance is
the ledger minus the charges. The rule above (check before the first
call, the usage row is the debit, no price means no start) is unchanged.
How rag groups its rows into actions is 431fb4a0-21c6-43ef-af1f-132c10ea43c2 below.

## Every usage row is booked under its user action; an output is one action, judge rounds included

**Id:** 431fb4a0-21c6-43ef-af1f-132c10ea43c2
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the coordinator's finance brief, 2026-10-14 (the actions, one action_id per user action); the coordinator's decision the same day that an output's judge rounds belong to the output; core's interface from G
**Revisit when:** an action starts to span several requests (a proposal and the chart made from it), or pricing rules need finer actions than rag books
**See:** https://github.com/oliver-zehentleitner/lasteverLM — d0bef660-f3ce-4834-b27e-5775151d11be — as of 2026-10-14

Every model call rag makes carries a `Booking`: who pays, the notebook,
the action (`chat_answer`, `output:<kind>`, `chart_propose`, `judge`,
`voice_sample`) and one `action_id` per user action. An output's id is
its `action_id`. That covers every attempt, all TTS segments, both calls
of a decision, and the judge's rounds and revisions in generation. A
judgement on request is a `judge` action of its own, and a chart proposal
is separate from the chart made from it.

**Reason:** core books a fixed fee once per `action_id`, so the grouping
decides what a user is charged for. One output is one thing the user
asked for. Retries are the service's problem, so they must not add a
fee, and a judge chosen for an output is part of "this output with a
judge", one price, as the coordinator decided. A judgement asked for
later is a separate request with its own price. The proposal and the
chart are two requests the user makes separately. An output's own id
needs no new column and is the same in every attempt, even one taken
over from a dead worker.

**Rejected alternatives:**
- A fresh `action_id` per attempt: a retry would charge the fee again.
- Generation-time judge rounds under `judge`: two prices for one output.
- One action for a proposal and its chart: the proposal may never be
  turned into a chart.

