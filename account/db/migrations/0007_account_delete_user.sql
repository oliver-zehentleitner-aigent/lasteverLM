-- lasteverLM-account: deleting a user. Vouchers survive their creator and their redeemer
-- as history (amount, dates), so both references may be empty. Plain PostgreSQL, safe to re-run.

alter table vouchers alter column created_by drop not null;
