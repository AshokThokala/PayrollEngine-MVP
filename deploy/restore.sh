#!/usr/bin/env bash
# Restore the database from a backup made by backup.sh. This REPLACES the current data.
#   ~/clearpay4u/deploy/restore.sh ~/backups/clearpay4u-2026-11-10-0230.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."
FILE="${1:?usage: deploy/restore.sh <backup.sql.gz>}"
[ -f "$FILE" ] || { echo "No such file: $FILE"; exit 1; }
read -r -p "This replaces ALL current data with $FILE. Type RESTORE to continue: " answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }
COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"
$COMPOSE stop api
gunzip -c "$FILE" | $COMPOSE exec -T db psql -U payroll -d payroll -v ON_ERROR_STOP=1 -q
$COMPOSE start api
echo "Restored from $FILE"
