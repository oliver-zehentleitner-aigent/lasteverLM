# Finance

## Vultr billing is fetched inside the account service, with the key in account's Secret

**Id:** 55fd45cc-47e5-4a3c-a831-323bda3c86ea
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** fleet coordination with infra, 2026-10-14 (maintainer go for the finance area)
**Revisit when:** account's egress gets restricted, Vultr offers a read-only billing scope, or the sync needs more than two endpoints

With `VULTR_BILLING_API_KEY` set, the account process reads
`GET /v2/billing/pending-charges` and the items of the last three invoices once a day
(and on `POST /admin/finance/infra/sync`) and upserts monthly lines into `infra_costs`
keyed by (month, source, item). Every replica may run it; the upsert makes a double
run harmless. Without the key, or with an empty one, nothing runs and the API says
`"vultr": "not connected"`. Amounts stay in USD as billed; the pricing rules' `usd_per_eur`
— the one rate core also books with — converts them, and without a rate the EUR totals
are null rather than estimated. (Until 2026-10-14 account kept its own `eur_per_usd`
setting for this; it went when core's booking got the rate, so there are not two rates.)

**Reason:** the result has to land in account's database and be shown by account's
API. Fetching in-process needs nothing new: no internal write endpoint, no second
token, no extra image or schedule. The pods already hold more sensitive secrets than
this key (session secret, voucher key, database URL).

**Rejected alternatives:** a Kubernetes CronJob with its own Secret, so the account
pods never see the key — rejected because the job cannot reach the database and
would need an internal endpoint on account plus a token to report its results,
which is more attack surface than the key it protects; a fixed exchange rate in code
— rejected because a silently wrong conversion is worse than an empty field (the
seeded 1.1188 of migration 0010 is a value in the editable rules, not in code).

**Consequence:** the account pods hold a Vultr key with the billing permission. Vultr
has no read-only billing scope, so the key can do what that permission allows, which
is less than an account key; it is still a credential to rotate if a pod is
compromised. Account's egress must keep 443 to api.vultr.com open.

## Profit counts only money: demo usage apart, infrastructure only with a known rate

**Id:** f89faf54-14f5-4f28-bdba-130b0e0ff070
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** implementation of the maintainer's finance brief, 2026-10-14; currency of MODEL_PRICES confirmed by the coordinator, 2026-10-14
**Revisit when:** the rate is fetched automatically (ECB) instead of set by an admin, or the demo user gets real money behind it

`/admin/finance/profit` is charged − model cost − infrastructure per day or month. The
demo user's usage is reported beside it, not in it: its credit is the migration's seed,
no one paid for it. Infrastructure enters a month as its EUR sum; a USD line without an
admin-set rate makes that month's infrastructure and profit null instead of estimated.
Daily rows get an even share of their month's infrastructure. Balances round down to
whole cents (never in the user's favour), shown charges round up.

**Reason:** a profit figure is only useful if every term in it is money that moved;
seed credit and a guessed exchange rate would make it look better or worse than it is
with no visible cause. Spreading a month's infrastructure evenly is the simplest rule
that makes daily rows add up to the month.

**Rejected alternatives:** counting the demo user's charges as revenue — rejected, they
are funded by the seed, not by anyone; converting with a built-in default rate —
rejected as above (finance.md, the Vultr entry); attributing infrastructure to the
first day of the month — rejected because daily profit would swing for no reason.

**Currency:** `MODEL_PRICES` are USD cents per million units from Vultr's catalog. Core
converts at booking with the pricing rules' `usd_per_eur` and stores the rate per row:
`cost_usd_cents` as measured, `cost_cents` and `charge_cents` in euro cents. Account
reads those and never converts usage itself, so every service shows the same figures;
it converts infrastructure with the same rate. The rate is required (core refuses to
book without it); migration 0010 seeds 1.1188, the ECB reference rate of 2026-10-13,
until the maintainer confirms one, and the pricing reset keeps the rate. (Earlier
versions of this entry first assumed EUR prices, then described USD usage amounts
before core converted at booking.)

## The exchange rate is the ECB's, fetched hourly, with a manual override that pauses it

**Id:** 8295ff9e-786e-43a5-9ae7-c0f50fa7fca5
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14
**Revisit when:** the platform bills in another currency, or the ECB stops publishing the daily XML

The account process reads the ECB's daily reference rates
(`eurofxref-daily.xml`) every hour; the USD rate is dollars per euro, exactly the
pricing rules' `usd_per_eur`. When it differs from the stored one it is written into the
pricing row; its ECB day, the last check, the last success and any error live in the
setting `exchange_rate` (core's `PricingRules.parse` accepts no extra keys in the pricing
row). A failed fetch keeps the stored rate and records the error; the status turns
stale after three days without a successful fetch. An admin who stores another rate
overrides it: the mode turns manual and the hourly update pauses until switched back.
Bookings keep the rate they were made with (core stores it per row).

**Reason:** the maintainer wants the rate to follow the market without anyone keeping
it. The ECB publishes once per working day, so an hourly check changes the rate at most
once a day and costs a small public download; checking hourly instead of daily means a
missed publication is picked up within the hour.

**Rejected alternative:** a fixed rate maintained by hand — the maintainer's choice
against it; a hand-kept rate drifts silently between updates. Fetching inside core at
booking time — rejected because every booking would depend on an outside service being
up; the rules row is read with a 30-second cache and the fetch runs beside the booking,
not in it.

