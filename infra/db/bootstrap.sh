#!/bin/sh
# One-time database bootstrap, idempotent: application role, database, pgvector.
# Runs as the admin role. Needs: psql, DATABASE_ADMIN_URL (any database on the
# instance), APP_DB_PASSWORD; optional APP_DB_USER, APP_DB_NAME (lasteverlm).
set -eu
: "${DATABASE_ADMIN_URL:?}" "${APP_DB_PASSWORD:?}"
user=${APP_DB_USER:-lasteverlm}
db=${APP_DB_NAME:-lasteverlm}

psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 -q -X -v user="$user" -v pw="$APP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'user', :'pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'user') \gexec
SELECT format('ALTER ROLE %I WITH PASSWORD %L', :'user', :'pw') \gexec
SQL
psql "$DATABASE_ADMIN_URL" -v ON_ERROR_STOP=1 -q -X -v user="$user" -v db="$db" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec
SQL
# The extension lives in the application database; CREATE EXTENSION needs the admin role.
# The application role owns its database but is neither superuser nor allowed to create extensions.
appdb=$(printf '%s' "$DATABASE_ADMIN_URL" | sed -E "s#(://[^/]+)/[^?]*#\1/$db#")
psql "$appdb" -v ON_ERROR_STOP=1 -q -X -c "CREATE EXTENSION IF NOT EXISTS vector"
echo "bootstrap done: role $user, database $db, extension vector"
