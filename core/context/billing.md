# Billing

## Cost and charge are fixed when a row is booked; a fee once per action

**Id:** d0bef660-f3ce-4834-b27e-5775151d11be
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's go for the finance redesign, 2026-10-14, design relayed by the coordinating agent
**Revisit when:** a charge has to change after the fact (refunds, a price correction applied to past usage)

Every `usage` row carries two amounts:

- `cost_cents`: what the call really cost, its units at `MODEL_PRICES`.
- `charge_cents`: what the user pays, the cost times
  `1 + margin_pct / 100` under the pricing rules in account's `settings`
  row `pricing`.

Rules for the charge:

- An action's own margin wins over the default margin.
- `record_usage` computes both amounts at booking and writes them into
  the row. The balance sums `charge_cents`; nothing reprices old rows.
- An action may also have a fixed fee. It is booked as its own row of
  kind `fee` (cost 0, charge the fee), once per `action_id` (a partial
  unique index plus `on conflict do nothing`), never per usage row.
- Both amounts are exact numerics, no longer rounded up to a whole cent
  per call. With a margin on top, per-call rounding would have charged a
  thousandth-of-a-cent embedding as a full cent, and the margin would be
  noise next to that rounding.

**Reason:**
- History has to survive a change of the rules. A user's balance, an
  admin's revenue figures and a past action's price must stay what they
  were when the margin moves.
- One action such as an audio output books many rows, one per TTS
  segment. A per-row fee would charge it by its length, not once.

**Rejected alternative:** apply the margin at read time (store the cost
only, multiply when summing). Rejected: every change of the margin would
rewrite every past balance and every report.

**Rejected alternative:** bake the margin into `MODEL_PRICES`. Rejected:
the real cost would be lost, so cost and revenue could no longer be told
apart. A margin per action, rather than per model, would also be
impossible.

## Migration 0006 is an expand step; a trigger fills rows of the previous release

**Id:** ff6a81c6-6ddb-4446-af8c-4e61efa61d8e
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the coordinating agent's deploy review of the finance redesign, 2026-10-14
**Revisit when:** the release after 0006 is deployed everywhere: then the contract migration sets the columns not null and drops the trigger

`action`, `action_id` and `charge_cents` are nullable for now. A `before
insert` trigger, `core_usage_fill_billing`, fills a missing one:

- `action` becomes `unknown`;
- `action_id` becomes the row's id;
- `charge_cents` becomes `cost_cents`.

Readers sum `coalesce(charge_cents, cost_cents)`. `record_usage` still
refuses `unknown`, so only old code produces it.

**Reason:** migrations run as a hook before the pods roll. For a minute
or two, pods of the previous release keep booking rows without the new
columns. A `not null` would make those inserts fail after the provider
call had already been billed, and the cost would be lost. Ingest's
library migrations (0003 expand, 0004 contract) set the precedent.

**Rejected alternative:** `not null` with defaults in one migration.
Rejected: no column default can give `action_id` the row's own id or
`charge_cents` the row's cost, which is what the old rows mean.
