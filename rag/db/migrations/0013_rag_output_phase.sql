-- lasteverLM rag: what a running output is doing right now (expand only).
--
-- The worker writes the step it has really begun (retrieving, writing,
-- judging round 2 of 3, ...) with the claim's heartbeat, in the same update;
-- it is cleared when the output is ready or failed. NULL for every row of
-- the previous release.

alter table outputs add column if not exists phase jsonb;
