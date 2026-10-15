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


## Without an exchange rate nothing that calls a model runs

**Id:** 78aa59d2-c992-4d45-8793-0c9371e6acfe
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the coordinator, 2026-10-14, on a finding of ingest's: booking without `usd_per_eur` fails after the model call; core's currency entry (US cents measured, euro cents charged, no default rate)
**Revisit when:** core books in one currency again, or gives the rate a default

The credit check (`require_credit`) reads the pricing rules first. When
they have no `usd_per_eur`, every request that would call a model (an
answer, an output, a proposal, a judgement, a preview) and the estimate
answer 503 "pricing has no exchange rate, ask an admin" before any
provider call. The worker reads the rules before claiming and, without a
rate, claims no job and logs an error each pass.

**Reason:** core refuses to book a dollar cost as euros without a rate,
and the booking comes after the call. A call made without a rate is
paid to the platform and never charged. Checking first turns that silent
loss into a visible refusal. A claimed job counts an attempt, so a worker
that claimed and failed would use up the user's three attempts on a
configuration gap. Not claiming leaves the jobs waiting until the rate is
set.

**Rejected alternatives:**
- Letting the booking fail after the call: the platform is paid, the
  user is not charged.
- Claiming jobs and failing them: it spends attempts and fails outputs
  for a problem the user cannot fix.

## Credit is checked once, when an action starts; an action that started runs to the end

**Id:** b93ff000-d488-4930-b11c-4d1e9840e1ee
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer order relayed by the coordinator, 2026-10-15 (an action that started finishes even if the balance goes negative; never spend most of it and then stop; check once at the start; a slightly negative balance is accepted)
**Revisit when:** a single action can cost a large multiple of a typical balance, so that running it to the end leaves balances deeply negative

Every action checks the balance once, when it starts: a chat answer, an
output's creation, a judgement on request, a voice sample, and an agent
plan at confirm. After that nothing checks again. An output's worker
runs every attempt, judge round, revision and audio segment, and a
confirmed plan runs every step, its outputs and explanations included,
even when the balance goes negative on the way. A plan without credit at
confirm answers 402 and stays proposed, with nothing run.

**Reason:** an action stopped half way has spent the user's money on
something they cannot use: a plan with its source added but no output, an
output paid for up to its last judge round but never finished. Running to
the end costs at most one action's overrun, which the next top-up covers,
and the user gets what they paid for. Checking once at the start still
keeps a user without credit from starting anything.

**Rejected alternatives:**
- Checking before every step or call: stops an action half done, after
  most of its cost is spent (a confirmed plan did this before each step
  until this decision).
