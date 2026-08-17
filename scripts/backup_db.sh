#!/usr/bin/env bash
# Nightly Postgres backup for the production ledger database.
#
# Design notes (see DEPLOY.md "Backups" section for the full procedure):
#   - Dumps happen *inside* the db container via `docker compose exec`, using
#     the container's own POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB
#     environment variables — this script never reads, echoes, or embeds
#     any credential itself. `set -x` is deliberately never used here for
#     the same reason (it would otherwise print the pg_dump command line,
#     which is fine, but keeps the discipline of never doing so).
#   - Every dump is verified immediately (gzip integrity + a plausibility
#     check on the SQL header) before it's trusted — a silently-corrupt
#     backup is worse than a missing one, because nobody notices until the
#     restore that needed it fails too.
#   - Retention is local-disk only today: KEEP_DAYS of dumps are kept, older
#     ones pruned. This is *not* sufficient on its own — see the "Off-box
#     storage" note in DEPLOY.md. A local-disk failure or an accidental
#     `docker volume rm` takes out the database AND every backup this
#     script has ever made. Shipping these off-box (rclone to S3/Backblaze,
#     or a periodic scp to a second host) needs storage credentials this
#     environment doesn't have configured — documented as a required
#     follow-up, not silently skipped.
#   - Exits non-zero on any failure so cron/systemd correctly flags the run
#     as failed (cron mails root on non-zero exit + any stderr output, if
#     mail delivery is configured on the host — see DEPLOY.md).
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-/root/backups}"
LOG_FILE="${LOG_FILE:-$BACKUP_DIR/backup.log}"
KEEP_DAYS="${KEEP_DAYS:-14}"
LOCK_FILE="${LOCK_FILE:-$BACKUP_DIR/.backup.lock}"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
DEST="$BACKUP_DIR/backup-$TIMESTAMP.sql.gz"

cd "$(dirname "$0")/.."
mkdir -p "$BACKUP_DIR"

log() {
    echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE" >&2
}

fail() {
    log "FAILED: $*"
    exit 1
}

# Concurrent-run guard: if a previous run is somehow still going (e.g. an
# unusually large database made the last run overrun into this one's
# scheduled start), don't let a second pg_dump start stacked on top of it —
# `flock -n` fails fast instead of queuing, so cron's next scheduled
# attempt just skips cleanly rather than piling up processes. Held for the
# whole script (this fd stays open until the process exits), not just the
# dump step, so retention pruning below can't race a concurrent run either.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "Another backup run is already in progress (lock: $LOCK_FILE) — skipping this run."
    exit 0
fi

# Crash-safety, part 1: a graceful termination (SIGTERM — `docker compose
# down`, systemd stopping the unit, a plain `kill`) still runs this trap,
# so the common case cleans up after itself immediately.
trap 'rm -f "$DEST.partial"' EXIT

# Crash-safety, part 2: SIGKILL cannot be trapped by any process, ever —
# that's what makes it SIGKILL — and it's specifically what the Linux OOM
# killer sends. Part 1's trap does nothing in that case, so a `.partial`
# from a run killed that way would sit in $BACKUP_DIR forever (retention
# below only prunes the `backup-*.sql.gz` pattern, which `.partial` never
# matches). Instead, sweep any `.partial` older than an hour at the start
# of every run — no legitimate run of this script takes anywhere near that
# long, so anything that old is unambiguously orphaned, not a concurrent
# run in progress (that case is already handled by the flock above).
find "$BACKUP_DIR" -maxdepth 1 -name '*.sql.gz.partial' -mmin +60 -print -delete \
    | while read -r stale; do log "Swept stale partial (orphaned by a killed run): $stale"; done

log "Starting backup -> $DEST"

if ! docker compose -f "$COMPOSE_FILE" exec -T db \
    sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip > "$DEST.partial"; then
    rm -f "$DEST.partial"
    fail "pg_dump/gzip pipeline exited non-zero"
fi

# Verify before trusting: gzip integrity, then a plausibility check that
# this is actually a pg_dump SQL stream and not an empty/truncated file
# (e.g. from the db container being unhealthy mid-dump).
if ! gzip -t "$DEST.partial" 2>/dev/null; then
    rm -f "$DEST.partial"
    fail "backup failed gzip integrity check"
fi

# Subshell with pipefail off: `head -c 4096` closing its read end early
# sends SIGPIPE back up to `zcat`, which pipefail would otherwise treat as
# a pipeline failure even though grep found exactly what it was looking
# for — that's a false alarm about the verification harness, not the dump.
if ! (set +o pipefail; zcat "$DEST.partial" | head -c 4096 | grep -q "PostgreSQL database dump"); then
    rm -f "$DEST.partial"
    fail "backup does not look like a valid pg_dump (missing expected header)"
fi

SIZE_BYTES=$(stat -c%s "$DEST.partial")
if [ "$SIZE_BYTES" -lt 1024 ]; then
    rm -f "$DEST.partial"
    fail "backup is suspiciously small (${SIZE_BYTES} bytes) — refusing to keep it"
fi

mv "$DEST.partial" "$DEST"
log "OK: $DEST (${SIZE_BYTES} bytes, verified)"

# Retention: prune local dumps older than KEEP_DAYS. Never touches anything
# that isn't this script's own backup-*.sql.gz naming pattern, and never
# touches the pre-existing manual snapshots (pre-deploy-*.sql.gz) from
# before this script existed.
find "$BACKUP_DIR" -maxdepth 1 -name 'backup-*.sql.gz' -mtime "+$KEEP_DAYS" -print -delete \
    | while read -r pruned; do log "Pruned (older than ${KEEP_DAYS}d): $pruned"; done

log "Backup run complete."
