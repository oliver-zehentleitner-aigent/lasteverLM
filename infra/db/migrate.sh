#!/bin/sh
# Applies the migrations of every service in a fixed order, each file once,
# each in its own transaction. Layout of the root directory:
#   <root>/<service>/NNNN_<topic>.sql   for service in $MIGRATE_ORDER
# A file is recorded in schema_migrations as "<service>/NNNN_<topic>" so the
# per-repository numbering cannot collide. Files may use the psql variable
# :EMBEDDING_DIMENSION (e.g. vector(:EMBEDDING_DIMENSION)).
# Needs: psql on the path, DATABASE_URL; optional EMBEDDING_DIMENSION (1536).
# Usage: migrate.sh <root>
set -eu

root=${1:?usage: migrate.sh <root>}
: "${DATABASE_URL:?DATABASE_URL is not set}"
order=${MIGRATE_ORDER:-"infra core account ingest rag"}
dim=${EMBEDDING_DIMENSION:-1536}

psql_q() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -v EMBEDDING_DIMENSION="$dim" -q -X -t -A "$@"; }

psql_q -c "CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)"

applied=$(psql_q -c "SELECT version FROM schema_migrations ORDER BY version")
count=0
for svc in $order; do
    dir="$root/$svc"
    if [ ! -d "$dir" ]; then
        echo "missing migrations directory: $dir (service $svc)" >&2
        exit 1
    fi
    for f in "$dir"/[0-9][0-9][0-9][0-9]_*.sql; do
        [ -e "$f" ] || continue
        v="$svc/$(basename "$f" .sql)"
        if printf '%s\n' "$applied" | grep -qx "$v"; then
            continue
        fi
        echo "applying $v"
        psql_q --single-transaction -f "$f" -c "INSERT INTO schema_migrations (version) VALUES ('$v')"
        count=$((count + 1))
    done
done
echo "done: $count migration(s) applied (embedding dimension $dim)"
