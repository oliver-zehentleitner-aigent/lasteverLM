-- lasteverLM ingest: a prompt retry after a transient failure.
-- Before, a failed attempt kept its claim and the next attempt waited for
-- the stale-claim timeout (CLAIM_TIMEOUT_SECONDS, 10 minutes). Now the
-- worker releases the claim and sets retry_at a few seconds ahead (growing
-- per attempt); the claim query skips a row until its retry_at has passed.
alter table library_sources add column if not exists retry_at timestamptz;
