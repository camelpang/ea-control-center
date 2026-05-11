# GitHub To Server Deployment

This is the recommended production-testing flow:

1. Commit locally.
2. Push to GitHub.
3. SSH into the server.
4. Pull the latest code.
5. Rebuild services.
6. Run migrations.
7. Run production smoke tests.

## 1. Local Checks Before Pushing

Before committing, confirm sensitive and local files are not staged:

```bash
git status --short
```

Never commit:

- `.env`
- `.env.*` except `.env.example`
- local database files such as `*.db`, `*.sqlite`, `*.sqlite3`
- `.local/`
- logs
- `__pycache__/`, `*.pyc`
- `.pytest_cache/`
- `.vscode/`

Run tests locally when possible:

```bash
uv run --python 3.13 --with-requirements backend/requirements.txt pytest backend/tests/test_api_smoke.py
```

Commit and push:

```bash
git add .
git commit -m "Prepare production deployment flow"
git push origin main
```

## 2. First-Time Server Setup

Clone the repository:

```bash
sudo mkdir -p /opt
cd /opt
git clone https://github.com/YOUR_ORG/YOUR_REPO.git ea-control-center
cd /opt/ea-control-center
```

Create production `.env` on the server only:

```bash
cp .env.example .env
vim .env
```

Required production values:

```text
POSTGRES_PASSWORD
DATABASE_URL
EA_API_TOKEN
ADMIN_API_TOKEN
JWT_SECRET
ALLOW_PUBLIC_DASHBOARD_PREVIEW=false
```

Generate strong secrets:

```bash
openssl rand -hex 32
```

Make scripts executable:

```bash
chmod +x scripts/*.sh
```

Start services and migrate:

```bash
docker compose up -d --build
docker compose exec -T backend alembic -c /app/alembic.ini upgrade head
```

Run a read-only smoke test:

```bash
export ADMIN_API_TOKEN="your_admin_token"
scripts/production-smoke-test.sh http://127.0.0.1:8000
```

## 3. Normal Update Flow

For later updates, run:

```bash
cd /opt/ea-control-center
chmod +x scripts/*.sh
BRANCH=main BASE_URL=http://127.0.0.1:8000 scripts/server-update.sh
```

The update script does:

- load server `.env`
- back up PostgreSQL into `backups/`
- `git fetch`
- `git pull --ff-only`
- `docker compose up -d --build`
- Alembic migration inside the backend container
- `docker compose ps`
- read-only production smoke test

Useful options:

```bash
RUN_BACKUP=0 scripts/server-update.sh
RUN_SMOKE=0 scripts/server-update.sh
BRANCH=staging scripts/server-update.sh
BASE_URL=https://your-domain.example scripts/server-update.sh
```

## 4. Manual Backup

Run this before risky changes or manual database work:

```bash
cd /opt/ea-control-center
scripts/backup-postgres.sh
```

Backups are written to:

```text
/opt/ea-control-center/backups/
```

## 5. Optional Write Smoke Test

Only run this against a safe test EA ID. It writes a heartbeat and creates then cancels a non-trading `update_params` command.

```bash
cd /opt/ea-control-center
export ADMIN_API_TOKEN="your_admin_token"
export EA_API_TOKEN="your_ea_token"
export WRITE_SMOKE=1
export SMOKE_EA_ID="production-smoke-ea"
scripts/production-smoke-test.sh http://127.0.0.1:8000
```

## 6. Rollback

If a deployment fails after `git pull` but before live testing:

```bash
cd /opt/ea-control-center
git log --oneline -5
git checkout <previous_commit_sha>
docker compose up -d --build
docker compose exec -T backend alembic -c /app/alembic.ini upgrade head
```

If the database needs rollback, restore from the latest backup only after stopping traffic and confirming the target backup:

```bash
docker compose stop backend
docker exec -i ea-postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backups/your_backup.sql
docker compose up -d backend
```

For destructive restores, prefer testing on a copied database first.

## 7. After Deployment

Open `/admin` and check:

- `系统自检`
- EA account visibility
- dedicated per-EA token status
- `/commands`
- `/audit-logs`

Connect one low-risk EA first, verify heartbeat and snapshot, then continue controlled production testing.
