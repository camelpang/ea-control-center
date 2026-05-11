# Production Readiness Checklist

Use this checklist before deploying to a server for production testing.

If you deploy by pushing to GitHub and pulling on the server, follow:

```text
docs/github-server-deploy.md
```

## 1. Clean Upload Package

Do not upload local-only files:

- `.env`
- `.env.*` except `.env.example`
- `.local/`
- `data/`
- `*.db`, `*.sqlite`, `*.sqlite3`
- `*.log`
- `__pycache__/`, `*.pyc`
- `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- `.venv/`
- `.vscode/`

If you ever copy files directly instead of using GitHub, use an exclude list like this from the project parent directory:

```bash
rsync -av --delete \
  --exclude ".git" \
  --exclude ".env" \
  --exclude ".env.*" \
  --exclude ".local" \
  --exclude "data" \
  --exclude "*.db" \
  --exclude "*.sqlite" \
  --exclude "*.sqlite3" \
  --exclude "*.log" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude ".pytest_cache" \
  --exclude ".venv" \
  ea-control-center/ user@server:/opt/ea-control-center/
```

## 2. Production `.env`

Create `.env` on the server from `.env.example`, then replace every example secret.

Required changes:

```text
POSTGRES_PASSWORD
DATABASE_URL
EA_API_TOKEN
ADMIN_API_TOKEN
JWT_SECRET
ALLOW_PUBLIC_DASHBOARD_PREVIEW=false
```

Recommended:

- Use long random values for `EA_API_TOKEN`, `ADMIN_API_TOKEN`, and `JWT_SECRET`.
- Keep `ALLOWED_TRADE_SYMBOLS=XAUUSD` unless production testing intentionally includes other symbols.
- Set `MAX_MANUAL_ORDER_VOLUME` to the maximum test size you are willing to allow.
- Generate dedicated per-EA tokens from `/ea-accounts` for live EA instances.

Example secret generation:

```bash
openssl rand -hex 32
```

## 3. Database And Migration

Start services:

```bash
docker compose up -d --build
```

Run migrations:

```bash
docker compose exec backend alembic -c /app/alembic.ini upgrade head
```

If Alembic files are mounted differently in your deployment, run the same command from the backend project directory before starting live traffic:

```bash
cd /opt/ea-control-center/backend
alembic upgrade head
```

## 4. Backup Before Testing

Create a PostgreSQL backup before connecting live EAs:

```bash
mkdir -p /opt/ea-control-center/backups
docker exec ea-postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "/opt/ea-control-center/backups/ea_control_$(date +%Y%m%d_%H%M%S).sql"
```

Verify the backup file is not empty:

```bash
ls -lh /opt/ea-control-center/backups
```

## 5. Network And Access

- Keep Uvicorn bound behind Docker or a reverse proxy; do not expose it directly to the public internet.
- Put the admin UI behind HTTPS, preferably Nginx or another reverse proxy.
- Open only required firewall ports.
- Keep PostgreSQL and Redis private to the Docker network.
- Confirm `/api/dashboard-preview` is not public unless a demo wall is intentional.

## 6. Application Checks

After deployment:

```bash
curl http://127.0.0.1:8000/health
chmod +x scripts/production-smoke-test.sh
ADMIN_API_TOKEN="your_admin_token" scripts/production-smoke-test.sh http://127.0.0.1:8000
```

In the admin UI:

- Open `/admin`.
- Check `系统自检`.
- Confirm database is healthy.
- Confirm token and JWT warnings are gone.
- Confirm trading safety config shows the intended symbol whitelist and volume cap.
- Create or log in as an admin user.
- Generate dedicated EA tokens from `/ea-accounts`.

## 7. Controlled Live Test

Use one demo or low-risk EA first:

- Confirm the EA reports heartbeat and snapshot.
- Confirm it appears in `/ea-accounts`.
- Assign it to the intended user.
- Confirm viewer users can only see assigned EAs.
- Confirm `can_trade=false` blocks command actions in the UI and API.
- Send only non-trading or low-risk commands first.
- Check `/commands` and `/audit-logs` after every action.
