-- lasteverLM core: cost and charge are separate (expand step).
--
-- `cost_usd_cents` is what a call really cost (measured units x
-- MODEL_PRICES, which are US cents as the platform lists them),
-- `usd_per_eur` the rate it was converted at, `cost_cents` that cost in
-- euro cents and `charge_cents` what the user pays in euro cents (the euro
-- cost plus the margin of the pricing rules, account's `settings` row
-- 'pricing', which also holds the rate). All are fixed at booking time
-- and exact: numeric, sub-cent, no rounding up per call. Credits are euro
-- cents. `action` names the user action a row belongs to (core's
-- USAGE_ACTIONS; 'unknown' only for rows from before this migration),
-- `action_id` groups all rows of one action. Kind 'fee' is the fixed fee of an action: cost 0, charge
-- the fee, at most one per action_id. The balance becomes
-- sum(ledger.amount_cents) - sum(usage.charge_cents).
--
-- Rows booked before this migration were priced in US cents and charged
-- one to one as euro cents; they keep that: cost_usd_cents = cost_cents,
-- charge_cents = cost_cents, usd_per_eur null (no rate was applied).
--
-- Expand only: the new columns stay nullable and a trigger fills them,
-- because pods of the previous release keep inserting rows without them
-- while the deploy rolls (migrations run before the pods change); for
-- that minute their dollar cost is still charged one to one. A later
-- migration, one release on, sets action, action_id, cost_usd_cents and
-- charge_cents not null and drops the trigger. Until then readers use
-- coalesce(charge_cents, cost_cents).

alter table usage alter column cost_cents type numeric using cost_cents::numeric;
alter table usage add column if not exists action text;
alter table usage add column if not exists action_id uuid;
alter table usage add column if not exists charge_cents numeric check (charge_cents >= 0);
alter table usage add column if not exists cost_usd_cents numeric check (cost_usd_cents >= 0);
alter table usage add column if not exists usd_per_eur numeric check (usd_per_eur > 0);

alter table usage drop constraint if exists usage_kind_check;
alter table usage add constraint usage_kind_check
    check (kind in ('llm', 'embedding', 'tts', 'stt', 'decision', 'fee'));

update usage set
    charge_cents = coalesce(charge_cents, cost_cents),
    cost_usd_cents = coalesce(cost_usd_cents, cost_cents),
    action_id = coalesce(action_id, id),
    action = coalesce(action, case kind
        when 'tts' then 'output:audio'
        when 'stt' then 'source:audio'
        when 'decision' then 'output:decision'
        else 'unknown'
    end)
where charge_cents is null or cost_usd_cents is null or action_id is null or action is null;

create or replace function core_usage_fill_billing() returns trigger
language plpgsql as $$
begin
    new.action := coalesce(new.action, 'unknown');
    new.action_id := coalesce(new.action_id, new.id);
    new.charge_cents := coalesce(new.charge_cents, new.cost_cents);
    new.cost_usd_cents := coalesce(new.cost_usd_cents, new.cost_cents);
    return new;
end;
$$;

drop trigger if exists usage_fill_billing on usage;
create trigger usage_fill_billing before insert on usage
    for each row execute function core_usage_fill_billing();

-- One fixed fee per action: the booking inserts it with on conflict do nothing.
create unique index if not exists usage_fee_action_idx on usage (action_id) where kind = 'fee';
