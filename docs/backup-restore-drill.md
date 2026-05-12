# Backup Restore Drill

This document describes how to prove that PostgreSQL backups can actually be restored before relying on them in production.

## Goal

The restore drill must not touch the live database. It restores a selected backup into a temporary drill database, validates core tables, then drops the drill database by default.

## Prerequisites

- Server `.env` exists and contains `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
- Docker Compose services are running.
- The PostgreSQL container name is `ea-postgres`, or set `POSTGRES_CONTAINER`.
- Scripts are executable:

```bash
chmod +x scripts/*.sh
```

## Create A Backup

```bash
cd /opt/ea-control-center
scripts/backup-postgres.sh
```

Confirm the backup file is not empty:

```bash
ls -lh backups/
```

## Run A Restore Drill

Use the latest backup file:

```bash
cd /opt/ea-control-center
scripts/restore-drill-postgres.sh backups/ea_control_YYYYmmdd_HHMMSS.sql
```

The script will:

1. Check the PostgreSQL container is ready.
2. Drop and recreate `ea_control_restore_drill`.
3. Restore the backup into that temporary database.
4. Print row counts for core tables.
5. Print the Alembic version if present.
6. Drop the temporary database.

## Keep The Drill Database For Manual Inspection

```bash
DROP_DRILL_DB=0 scripts/restore-drill-postgres.sh backups/ea_control_YYYYmmdd_HHMMSS.sql
```

Inspect manually:

```bash
docker exec -it ea-postgres psql -U "$POSTGRES_USER" -d ea_control_restore_drill
```

Clean up when done:

```bash
docker exec ea-postgres dropdb -U "$POSTGRES_USER" --if-exists ea_control_restore_drill
```

## Safety Rules

- Never set `DRILL_DB` equal to `POSTGRES_DB`; the script rejects this.
- Do not restore directly into production while EA traffic is active.
- Before any destructive production restore, stop backend traffic, confirm the exact backup file, and keep a second copy of the current database.
- Run a production smoke test after any real restore:

```bash
ADMIN_API_TOKEN="your_admin_token" scripts/production-smoke-test.sh http://127.0.0.1:8000
```

## Recommended Schedule

- Before every risky deployment or migration.
- After changing backup storage or server paths.
- At least once before production testing begins.
- Monthly during active production use.
