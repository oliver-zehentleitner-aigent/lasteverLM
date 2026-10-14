-- lasteverLM rag: the generation log of an output (what was retrieved, what
-- went into the prompt, which model, the usage, the support check), written
-- once when the output is ready and returned as Output.provenance. Outputs
-- from before have none.

alter table outputs add column if not exists provenance jsonb;
