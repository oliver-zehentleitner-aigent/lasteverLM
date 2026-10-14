-- lasteverLM-account: the pricing row core's booking needs. Plain PostgreSQL, safe to re-run.

-- Core books cost in US cents and charges in euro cents at the rules' usd_per_eur and
-- refuses to book without a rate (ExchangeRateMissingError). The row lives in account's
-- settings table, so account seeds it; core's migrations run before account's, on a fresh
-- database core would find no table. 1.1188 is the ECB euro reference rate of 2026-10-13,
-- a starting value: the service's hourly ECB sync replaces it, an admin can override it
-- manually. An existing row, rate or not, is never touched.
insert into settings (key, value)
values ('pricing', '{"usd_per_eur": 1.1188, "default_margin_pct": 0, "actions": {}}')
on conflict (key) do nothing;
