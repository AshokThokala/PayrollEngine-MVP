#!/usr/bin/env bash
# Deploy or update ClearPay4U on the server: pull the latest code, rebuild, restart, check health.
#   ~/clearpay4u/deploy/deploy.sh            # latest main
#   ~/clearpay4u/deploy/deploy.sh v1.2.0     # a tag or commit
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f deploy/.env ] || { echo "deploy/.env is missing - copy deploy/.env.example and fill it in"; exit 1; }
for key in DOMAIN ACME_EMAIL POSTGRES_PASSWORD SECRET_KEY FIELD_ENCRYPTION_KEY ADMIN_EMAIL ADMIN_PASSWORD; do
  grep -Eq "^${key}=.+" deploy/.env || { echo "Set ${key} in deploy/.env first"; exit 1; }
done

REF="${1:-main}"
echo "==> Fetching $REF"
git fetch --all --tags --quiet
git checkout --quiet "$REF"
[ "$REF" = "main" ] && git pull --quiet --ff-only origin main
echo "    at $(git log -1 --format='%h %s')"

# Back up before every update once the database exists.
if docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env ps --status running db 2>/dev/null | grep -q db; then
  echo "==> Backing up the database first"
  deploy/backup.sh
fi

COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"
echo "==> Building and starting"
$COMPOSE up -d --build --remove-orphans

DOMAIN=$(grep -E '^DOMAIN=' deploy/.env | cut -d= -f2-)
echo "==> Waiting for https://$DOMAIN/api/health"
for i in $(seq 1 60); do
  if curl -fsS "https://$DOMAIN/api/health" >/dev/null 2>&1; then
    echo "ClearPay4U is live at https://$DOMAIN"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 5
done
echo "Not answering on https://$DOMAIN yet. Check DNS and logs:"
echo "  $COMPOSE logs --tail=80 caddy api"
exit 1
