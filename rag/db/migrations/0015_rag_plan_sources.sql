-- lasteverLM rag: the sources a plan's outputs will read, shown with the plan
-- (expand only): the notebook's uploads, a web page with the age of its
-- cached version, and the pages the plan adds.

alter table plans add column if not exists sources jsonb;
