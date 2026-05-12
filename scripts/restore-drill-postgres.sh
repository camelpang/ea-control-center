#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
BACKUP_FILE="${1:-${BACKUP_FILE:-}}"
DRILL_DB="${DRILL_DB:-ea_control_restore_drill}"

cd "$ROOT_DIR"

if [[ -z "$BACKUP_FILE" ]]; then
  echo "ERROR: backup file is required." >&2
  echo "Usage: scripts/restore-drill-postgres.sh backups/ea_control_YYYYmmdd_HHMMSS.sql" >&2
  exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "ERROR: backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [[ ! -s "$BACKUP_FILE" ]]; then
  echo "ERROR: backup file is empty: $BACKUP_FILE" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

POSTGRES_DB="${POSTGRES_DB:-ea_control}"
POSTGRES_USER="${POSTGRES_USER:-ea_user}"
CONTAINER_NAME="${POSTGRES_CONTAINER:-ea-postgres}"

if [[ "$DRILL_DB" == "$POSTGRES_DB" ]]; then
  echo "ERROR: DRILL_DB must not equal production POSTGRES_DB ($POSTGRES_DB)." >&2
  exit 1
fi

echo "PostgreSQL restore drill"
echo "Container:   $CONTAINER_NAME"
echo "Source DB:   $POSTGRES_DB"
echo "Drill DB:    $DRILL_DB"
echo "Backup file: $BACKUP_FILE"

echo ""
echo "1. Verify PostgreSQL container"
docker exec "$CONTAINER_NAME" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo ""
echo "2. Recreate drill database"
docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DRILL_DB';" >/dev/null
docker exec "$CONTAINER_NAME" dropdb -U "$POSTGRES_USER" --if-exists "$DRILL_DB"
docker exec "$CONTAINER_NAME" createdb -U "$POSTGRES_USER" "$DRILL_DB"

echo ""
echo "3. Restore backup into drill database"
docker exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$DRILL_DB" -v ON_ERROR_STOP=1 < "$BACKUP_FILE" >/dev/null

echo ""
echo "4. Validate core tables"
CORE_TABLES=(
  users
  ea_instances
  account_snapshots
  commands
  audit_logs
)

for table in "${CORE_TABLES[@]}"; do
  count="$(docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$DRILL_DB" -Atc "SELECT COUNT(*) FROM $table;")"
  echo "$table rows=$count"
done

echo ""
echo "5. Validate Alembic version"
docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$DRILL_DB" -Atc "SELECT version_num FROM alembic_version LIMIT 1;" || true

if [[ "${DROP_DRILL_DB:-1}" == "1" ]]; then
  echo ""
  echo "6. Drop drill database"
  docker exec "$CONTAINER_NAME" dropdb -U "$POSTGRES_USER" --if-exists "$DRILL_DB"
else
  echo ""
  echo "6. Drill database kept because DROP_DRILL_DB=$DROP_DRILL_DB"
fi

echo ""
echo "Restore drill complete."
