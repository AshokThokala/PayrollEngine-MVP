#!/usr/bin/env bash
# Dump the database to ~/backups/clearpay4u-YYYY-MM-DD-HHMM.sql.gz and delete dumps older than
# BACKUP_KEEP_DAYS (default 14). Run nightly by cron (setup-server.sh) and before every deploy.
# Copy backups off the server too (Lightsail snapshots, or download them) - see LIGHTSAIL.md.
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP=$(grep -E '^BACKUP_KEEP_DAYS=' deploy/.env 2>/dev/null | cut -d= -f2-)
KEEP=${KEEP:-14}
DIR="$HOME/backups"
mkdir -p "$DIR"
chmod 700 "$DIR"
FILE="$DIR/clearpay4u-$(date +%F-%H%M).sql.gz"
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db \
  pg_dump -U payroll --clean --if-exists payroll | gzip > "$FILE"
chmod 600 "$FILE"
find "$DIR" -name 'clearpay4u-*.sql.gz' -mtime +"$KEEP" -delete
echo "$(date '+%F %T') backup written: $FILE ($(du -h "$FILE" | cut -f1))"
