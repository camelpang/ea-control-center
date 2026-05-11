#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
BRANCH="${BRANCH:-main}"
RUN_BACKUP="${RUN_BACKUP:-1}"
RUN_SMOKE="${RUN_SMOKE:-1}"

cd "$ROOT_DIR"

if [[ ! -f ".env" ]]; then
  echo "ERROR: .env not found. Create it from .env.example before updating." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source ".env"
set +a

if [[ -z "${ADMIN_API_TOKEN:-}" ]]; then
  echo "ERROR: ADMIN_API_TOKEN is required in .env for smoke testing." >&2
  exit 1
fi

echo "EA Control Center server update"
echo "Root:     $ROOT_DIR"
echo "Branch:   $BRANCH"
echo "Base URL: $BASE_URL"

if [[ "$RUN_BACKUP" == "1" ]]; then
  echo ""
  echo "1. Backup PostgreSQL"
  bash "$ROOT_DIR/scripts/backup-postgres.sh"
else
  echo ""
  echo "1. Backup skipped because RUN_BACKUP=$RUN_BACKUP"
fi

echo ""
echo "2. Pull latest code"
git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo ""
echo "3. Rebuild and start services"
docker compose up -d --build

echo ""
echo "4. Run database migrations"
docker compose exec -T backend alembic -c /app/alembic.ini upgrade head

echo ""
echo "5. Check containers"
docker compose ps

if [[ "$RUN_SMOKE" == "1" ]]; then
  echo ""
  echo "6. Run read-only production smoke test"
  ADMIN_API_TOKEN="$ADMIN_API_TOKEN" bash "$ROOT_DIR/scripts/production-smoke-test.sh" "$BASE_URL"
else
  echo ""
  echo "6. Smoke test skipped because RUN_SMOKE=$RUN_SMOKE"
fi

echo ""
echo "Server update complete."
