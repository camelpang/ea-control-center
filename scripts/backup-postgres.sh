#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

cd "$ROOT_DIR"

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
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_PATH="$BACKUP_DIR/${POSTGRES_DB}_${STAMP}.sql"

mkdir -p "$BACKUP_DIR"

echo "Backing up PostgreSQL database..."
echo "Container: $CONTAINER_NAME"
echo "Database:  $POSTGRES_DB"
echo "Output:    $BACKUP_PATH"

docker exec "$CONTAINER_NAME" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP_PATH"

if [[ ! -s "$BACKUP_PATH" ]]; then
  echo "ERROR: backup file is empty: $BACKUP_PATH" >&2
  exit 1
fi

echo "Backup complete: $BACKUP_PATH"
