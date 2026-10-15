# Billing

## Cost and charge are fixed when a row is booked; a fee once per action

**Id:** d0bef660-f3ce-4834-b27e-5775151d11be
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's go for the finance redesign, 2026-10-14
**Revisit when:** a charge has to change after the fact (refunds, a price correction applied to past usage)
**See:** https://github.com/oliver-zehentleitner/lasteverLM — 454bd7eb-b5a2-4c63-9544-6425f342a5a6 — as of 2026-10-15

Every `usage` row carries two amounts:

- `cost_cents`: what the call really cost, its units at `MODEL_PRICES`
  (converted from US cents to euro cents, see 05565ae9-d57c-4263-84d1-bf2162f8e3bb).
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
**Source:** the deploy review of the finance redesign, 2026-10-14
**Verification:** corroborated — re-checked 2026-10-15: releases after 0006 are deployed (v0.19.7 onward), so the contract step is due, but it has not been written; migration 0006 is still the latest and the columns are still nullable with the trigger in place, as described here
**Revisit when:** the contract migration is written (columns not null, trigger dropped); this entry is then superseded by the one that records it

`action`, `action_id`, `charge_cents`, `cost_usd_cents` and
`usd_per_eur` are nullable for now. A `before insert` trigger,
`core_usage_fill_billing`, fills the first four when missing:

- `action` becomes `unknown`;
- `action_id` becomes the row's id;
- `charge_cents` becomes `cost_cents`;
- `cost_usd_cents` becomes `cost_cents`.

`usd_per_eur` stays null for such a row: no rate was applied.

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

## Costs are US cents, charges euro cents, the rate is stored per row

**Id:** 05565ae9-d57c-4263-84d1-bf2162f8e3bb
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the account service's review of the finance redesign, 2026-10-14
**Verification:** corroborated — re-checked 2026-10-15: the rate's source is settled (account reads the ECB's daily rates every hour and writes `usd_per_eur` into the pricing row, with a manual override); core's part is unchanged: the rate is read from the rules, stored per row, and has no default
**Revisit when:** the platform bills in a currency other than US dollars, or credits are kept in a currency other than euros
**See:** https://github.com/oliver-zehentleitner/lasteverLM — 8295ff9e-786e-43a5-9ae7-c0f50fa7fca5 — as of 2026-10-15

`MODEL_PRICES` are US cents, as the platform lists them. Credits,
vouchers and balances are euro cents. `record_usage` books four
amounts:

- `cost_usd_cents`: the measured cost in US cents.
- `usd_per_eur`: the rate applied.
- `cost_cents`: the cost in euro cents, `cost_usd_cents / usd_per_eur`
  to ten decimal places.
- `charge_cents`: what the user pays, `cost_cents` times
  `1 + margin_pct / 100`.

The rate is `usd_per_eur` in the pricing rules, the same settings row as
the margins, so it has a single source. It is required and has no
default: rules without a rate, including the shipped defaults, make
`record_usage` raise `ExchangeRateMissingError` before it writes
anything. Account's migration seeded the row with the ECB reference
rate of 2026-10-13 (1.1188 US dollars per euro); since then account
keeps it current from the ECB (the entry linked above). The seed is in
account's migration, because the `settings` table is
account's and core's migrations run before it exists on a fresh
database. Rows booked before migration 0006 were charged one to one;
they keep that and get `usd_per_eur` null.

**Reason:** before this, a cost in dollars was charged as the same
number of euros. A rate fixed per row keeps a past charge, its cost and
the conversion reproducible after the rate moves.

**Rejected alternative:** convert `MODEL_PRICES` to euros up front.
Rejected: the platform's own figures would be lost, and every rate
change would mean editing the price table.

**Rejected alternative:** a default rate in code. Rejected: a stale
built-in number would charge wrongly without anyone noticing, which is
what failing loud is for.

**Rejected alternative:** `eur_per_usd`, euros per dollar. Rejected:
the ECB quotes dollars per euro, and storing its figure unchanged
avoids a rounded inverse.

**Rejected alternative:** seed the row in core's migration. Rejected
because of the table ownership and migration order above.

## A price list quotes observed costs through the current rules, one unit per action

**Id:** c6663f0d-f76d-42a1-9c1d-a72916980b57
**Type:** decision
**Status:** superseded
**Superseded by:** f584f5df-f447-457d-8dda-cb515bec8933
**Evidence:** confirmed
**Source:** the maintainer's go for a public price list, design agreed between the account service and core, 2026-10-14
**Revisit when:** a PDF should be priced per page, or an action needs a unit other than one action or a minute of audio
**See:** https://github.com/oliver-zehentleitner/lasteverLM — a41d8d48-87be-4c7b-ac67-169d82352225 — as of 2026-10-15

Every action has a unit in `USAGE_ACTION_UNITS`, next to
`USAGE_ACTIONS`. A test checks that both lists match. A unit is either
one action, counted once per `action_id` (`question`, `output`, `source`,
`check`, ...), or a minute of audio, counted as the `tts`/`stt` seconds in
`tokens_in` divided by 60. The unit is a stable key that the frontend
translates. The price is the observed euro cost of past actions put
through the current rules with `charge_for`, which applies the margin and
adds the fee once. A PDF is quoted per source. The typical range shows
how widely sources differ.

**Reason:** the unit is part of what an action is, so it lives in the
same place as the list of actions. A new action without a unit then
fails the test instead of a price list silently leaving it out.
Observed costs are what actions really took, and the current rules make
a changed margin visible at once.

**Rejected alternative:** price from the observed charges. Rejected:
they carry the rules in force when each row was booked, so after a
margin change the list would lag for as long as old rows dominate.

**Rejected alternative:** price from `MODEL_PRICES` and expected token
counts in the account service. Rejected: that would be a second pricing
path beside the booking, with guessed token counts.

**Rejected alternative:** a per-token unit ("tokens", marked as an
estimate). Rejected: it is not a price a user can act on.

**Rejected alternative, for now:** PDFs per page. The page count is
not in the usage rows. It would need a unit count per booking, a schema
change left for after the finance work.

## Core gives the price list its actions and the typical range; the per-unit price comes from the services' estimates

**Id:** f584f5df-f447-457d-8dda-cb515bec8933
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the account service's price list as implemented, 2026-10-15, after the maintainer chose per-unit estimates and per-page source prices
**Verification:** corroborated — re-checked 2026-10-15 against account's `service.py`: rows come from rag's and ingest's estimate endpoints, `USAGE_ACTION_UNITS` is used to decide which observed actions count, and `charge_for` turns their observed costs into the typical range
**Revisit when:** the price list needs a unit core should own (a per-page count in the usage rows), or `USAGE_ACTION_UNITS` is dropped or aligned with the units the list shows
**See:** https://github.com/oliver-zehentleitner/lasteverLM — 0253c931-53a0-4d42-a934-5503e9d37b62 — as of 2026-10-15

The public price list combines three parts:

- **Price per unit:** the services' own estimates. rag's estimate gives
  outputs, chat and the judge, ingest's estimate of one nominal unit
  gives sources. Sources are quoted per page, image, audio minute or web
  page, under unit keys the account service sets itself.
- **Typical range per whole action:** the observed euro costs of the
  last thirty days, put through the current rules with core's
  `charge_for`. So a changed margin shows at once, as before.
- **Which actions count:** `USAGE_ACTIONS` and `USAGE_ACTION_UNITS`.

What core keeps for this:

- the action list with a unit per action (a test keeps the two
  lists equal);
- `charge_for`.

The `unit` a source action has in core (`source`) is no longer what the
list shows. A PDF is no longer quoted per source.

**Reason:** the history-only price left most rows empty, because most
past usage predates the action tags. It also could not price a page it
never counted. The estimates are the numbers a user sees before
starting an action, so the list and the action agree. That decision and
its alternatives belong to the account service and are recorded there
(the linked entry). Core's part shrank to the action list and the one
formula.

**Rejected alternative:** add a page count to the usage rows so core's
units could price pages from history. Rejected for now: the estimates
already give a per-page price without a schema change.
