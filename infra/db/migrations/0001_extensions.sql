-- Infra-owned: extensions need the admin role, which only the migration Job has.
-- Every service's own migrations (core, account, ingest, rag) run after this file.
CREATE EXTENSION IF NOT EXISTS vector;
