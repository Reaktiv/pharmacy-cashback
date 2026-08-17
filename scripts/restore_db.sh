#!/usr/bin/env bash
# Restore a backup produced by backup_db.sh.
#
# SAFETY: this script refuses to run against a database that already has
# tables in it unless FORCE=1 is set — restoring into a live, populated
# production database would silently merge/duplicate/conflict with
# existing rows rather than cleanly overwrite them (pg_dump's plain-SQL
# output is not idempotent). The intended flow for a real disaster
# recovery is: point this at a *fresh* `db` container/volume, verify the
# restored data, then cut the app over to it — not restore in place over a
# database that's still serving traffic.
#
# Usage:
#   ./scripts/restore_db.sh /root/backups/backup-2026-08-17-0300.sql.gz
#   COMPOSE_FILE=docker-compose.yml ./scripts/restore_db.sh <file>   # local/dev target
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_FILE="${1:?Usage: $0 <path-to-backup.sql.gz>}"
FORCE="${FORCE:-0}"

cd "$(dirname "$0")/.."

[ -f "$BACKUP_FILE" ] || { echo "No such backup file: $BACKUP_FILE" >&2; exit 1; }

echo "Verifying backup integrity before restore..." >&2
gzip -t "$BACKUP_FILE" || { echo "Backup fails gzip integrity check — refusing to restore." >&2; exit 1; }

TABLE_COUNT=$(docker compose -f "$COMPOSE_FILE" exec -T db \
    sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "select count(*) from information_schema.tables where table_schema='"'"'public'"'"'"')

TABLE_COUNT=$(echo "$TABLE_COUNT" | tr -d '[:space:]')

if [ "$TABLE_COUNT" != "0" ] && [ "$FORCE" != "1" ]; then
    cat >&2 <<EOF
Refusing to restore: the target database already has $TABLE_COUNT table(s).
Restoring a plain-SQL dump into a non-empty database can duplicate or
conflict with existing data rather than cleanly replace it.

If you specifically intend to wipe and restore this database (e.g. a
scratch/throwaway target, never production with live traffic), re-run with
FORCE=1. This script will NOT do that for you automatically.
EOF
    exit 1
fi

echo "Restoring $BACKUP_FILE into the '$COMPOSE_FILE' db service..." >&2
zcat "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T db \
    sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

echo "Restore complete. Verify row counts / a few known records before trusting this." >&2
