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
`"vultr": "not connected"`. Amounts stay in USD as billed; an admin-set `eur_per_usd`
converts them, and without a rate the EUR totals are null rather than estimated.

**Reason:** the result has to land in account's database and be shown by account's
API. Fetching in-process needs nothing new: no internal write endpoint, no second
token, no extra image or schedule. The pods already hold more sensitive secrets than
this key (session secret, voucher key, database URL).

**Rejected alternatives:** a Kubernetes CronJob with its own Secret, so the account
pods never see the key — rejected because the job cannot reach the database and
would need an internal endpoint on account plus a token to report its results,
which is more attack surface than the key it protects; a fixed default exchange rate
— rejected because a silently wrong conversion is worse than an empty field.

**Consequence:** the account pods hold a Vultr key with the billing permission. Vultr
has no read-only billing scope, so the key can do what that permission allows, which
is less than an account key; it is still a credential to rotate if a pod is
compromised. Account's egress must keep 443 to api.vultr.com open.

## Profit counts only money: demo usage apart, infrastructure only with a known rate

**Id:** f89faf54-14f5-4f28-bdba-130b0e0ff070
**Type:** decision
**Status:** active
**Evidence:** inferred
**Source:** implementation of the maintainer's finance brief, 2026-10-14
**Revisit when:** model prices are configured in another currency than EUR, or infrastructure is billed in EUR, or the demo user gets real money behind it

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

**Open assumption:** `MODEL_PRICES` are read as EUR cents, because credits are EUR. If
the platform's model prices are entered in USD, cost needs the same conversion as
infrastructure; Evidence stays inferred until the maintainer confirms the currency.

