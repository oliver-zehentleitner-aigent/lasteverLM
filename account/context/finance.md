# Finance

## Vultr billing is fetched inside the account service, with the key in account's Secret

**Id:** 55fd45cc-47e5-4a3c-a831-323bda3c86ea
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision (the finance area), design agreed with infra, 2026-10-14
**Revisit when:** account's egress gets restricted, Vultr offers a read-only billing scope, or the sync needs more than two endpoints

With `VULTR_BILLING_API_KEY` set, the account process reads
`GET /v2/billing/pending-charges` and the items of the last three invoices once a day
(and on `POST /admin/finance/infra/sync`) and upserts monthly lines into `infra_costs`
keyed by (month, source, item). Every replica may run it; the upsert makes a double
run harmless. Without the key, or with an empty one, nothing runs and the API says
`configured: false` (until 2026-10-14 `"vultr": "not connected"`; split then into
`configured` and `last_success_at`, because "connected" next to an error read as a
contradiction). A failure keeps Vultr's own message, with a hint for its IP allow-list. Amounts stay in USD as billed; the pricing rules' `usd_per_eur`
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
**Source:** maintainer decision (the finance brief), 2026-10-14; currency of MODEL_PRICES confirmed with core, 2026-10-14
**Revisit when:** the rate is fetched automatically (ECB) instead of set by an admin, or the demo user gets real money behind it

`/admin/finance/profit` is charged − model cost − infrastructure per day or month. The
demo user's usage is reported beside it, not in it: its credit is the migration's seed,
no one paid for it. Infrastructure enters a month as its EUR sum; a USD line without a
rate makes that month's infrastructure and profit null instead of estimated.
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
the hourly ECB update replaces it (the exchange-rate entry below), and the pricing reset
keeps the rate. (Earlier
versions of this entry first assumed EUR prices, then described USD usage amounts
before core converted at booking.)

Re-checked 2026-10-15, after its `Revisit when` fired (the rate is now the ECB's,
fetched hourly): the rule still holds. The automatic rate only makes "no rate" rarer;
when it is missing, the figures stay null rather than estimated.

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

**Reason:** the rate should follow the market without anyone keeping it. The ECB publishes once per working day, so an hourly check changes the rate at most
once a day and costs a small public download; checking hourly instead of daily means a
missed publication is picked up within the hour.

**Rejected alternative:** a fixed rate maintained by hand — a hand-kept rate drifts
silently between updates. Fetching inside core at
booking time — rejected because every booking would depend on an outside service being
up; the rules row is read with a 30-second cache and the fetch runs beside the booking,
not in it.

## The public price list shows end prices from measured costs under today's rules

**Id:** a41d8d48-87be-4c7b-ac67-169d82352225
**Type:** decision
**Status:** superseded
**Superseded by:** 0253c931-53a0-4d42-a934-5503e9d37b62
**Evidence:** confirmed
**Source:** maintainer decision, design agreed with core, 2026-10-14
**Revisit when:** actions get a per-unit count beyond seconds (pages, words), or the window of 30 days is too short for rare actions

`GET /api/account/prices` is public. For each action users buy it takes the real euro
cost of every action_id of the last 30 days, runs it through the current pricing rules
(core's `charge_for`: margin plus the fee once) and reports p25, median and p75, and the
median divided by the action's units (core's `USAGE_ACTION_UNITS`; audio per minute from
the tts/stt seconds). Fewer than five actions give no number. The response holds end
prices, the unit, the model and the exchange rate — nothing else. `demo_seed` is left
out: the system books it, nobody buys it.
The judge appears once per level (`judge:low|medium|high`): its samples are split by the
model each call used, mapped to a level through `JUDGE_MODELS`, because the levels' models
cost about ten times apart (added 2026-10-14). The judge share of a generated output stays
inside that output's price; it cannot be told apart when judge and generator share a model.

**Reason:** users should see what an action costs before they spend credit. Measured
costs are what actions really need; today's rules make a margin change visible at once,
which past charges would hide for weeks. Five actions is the least that makes a median
mean something; below that a number would be a guess presented as a price.

Corrected the same day: the per-unit price now comes from the services' own estimates —
rag's `POST /estimate` with default options and ingest's `GET /estimate` of one nominal
unit — marked `estimated`, because history alone left almost every row empty (most past
usage predates the action tags). History still gives the typical range. Account calls
both as the demo user with a 60-second token and reads only their charge fields.

**Rejected alternatives:** publishing the margin and the fees beside the price —
rejected, the page is for buyers, the admin finance area keeps the margins; quoting
past charges — they show yesterday's rules; a per-token estimate from model prices —
dropped with core, a price per token is not one a user can reason about; pricing PDFs
per page — the usage rows hold no page count, a later contract change.


## The public price list shows estimated end prices per unit, history gives the typical range

**Id:** 0253c931-53a0-4d42-a934-5503e9d37b62
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, design agreed with core, rag and ingest, 2026-10-14; implementation
**See:** finance.md#the-public-price-list-shows-end-prices-from-measured-costs-under-todays-rules — a41d8d48-87be-4c7b-ac67-169d82352225 — as of 2026-10-15
**Revisit when:** an estimate and the measured history disagree widely for an action, or the 30-day window is too short for rare actions

`GET /api/account/prices` is public and cached five minutes. Each row's price per unit
comes from the services' own estimates — rag's `POST /estimate` with default options,
ingest's `GET /estimate` of one nominal unit — marked `estimated`, as a range
(`price_min_cents`, `price_max_cents`, the midpoint as `price_per_unit_cents`) and for
sources the part added once per source (`per_source_cents`). Sources are priced per
page, image, audio minute or web page; a PDF has one row read as text and one by
vision. Account calls both services as the demo user with a 60-second token and reads
only their charge fields. A failed estimate leaves that row's price empty. The typical
range per whole action (p25, median, p75) comes from the last 30 days of measured
costs through the current pricing rules; fewer than five actions give none. The judge
appears once per level. The response holds end prices, the unit, the model and the
exchange rate; no margin, fee or cost.

**Reason:** users should see what an action costs before they spend credit. History
alone left almost every row empty, since most past usage predates the action tags,
and it cannot price a unit it never counted; the estimate is the same number a user
sees before an action, so the list and the action agree. History still shows what
whole actions really cost, through today's rules so a margin change shows at once.

**Rejected alternatives:** the per-unit price from history only (the predecessor) —
empty rows and no page count; publishing the margin and the fees beside the price —
the page is for buyers, the admin finance area keeps the margins; quoting past
charges — they show yesterday's rules.

## The price list also comes as script-free HTML

**Id:** 97909649-2b48-4ab2-b1ce-17da55d977cf
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer bug report, 2026-10-14; `prices_page.py`

The web's `/prices` is a JavaScript-only page: a plain fetch gets the
empty shell, so ingest's URL loader read nothing when the starter notebook
used it as a source. `GET /api/account/prices/page` renders the same list
as plain HTML (title, headings, tables, every value escaped, no script,
CSP `default-src 'none'`), built from the same `PublicPrices` as
`GET /prices`, so the two cannot disagree. English only, in the web's
words; a test compares every row with the JSON.

**Reason:** the smallest change that gives a non-JavaScript reader the
real content, in the service that owns the data.

**Rejected alternatives:** server-side rendering of the whole web app —
far larger than one page needs, and a second rendering path for every
page; a headless browser in the URL loader — heavy to run in the cluster
and a new attack surface, executing arbitrary pages' scripts for every
URL source.
