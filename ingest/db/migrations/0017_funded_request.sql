-- lasteverLM ingest: a read funded when it was asked for.
-- An action starts only if the balance covers its estimated maximum plus
-- that of the owner's other funded reads still waiting; once started it
-- runs to the end. funded_request_at marks a queued source whose request
-- passed that check, funded_cents is its estimated maximum (what it holds
-- of the balance while it waits). The claim takes such a row whatever the
-- balance is by then; both are cleared when the read ends. Expand only.
alter table library_sources add column if not exists funded_request_at timestamptz;
alter table library_sources add column if not exists funded_cents numeric;
