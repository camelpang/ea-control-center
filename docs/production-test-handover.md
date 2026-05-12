# Production Test Handover

## Current Deployment

- Public entry: `http://47.86.170.144`
- Server path: `/opt/ea-control-center`
- Deployment branch: `main`
- Reverse proxy: Nginx listens on port `80` and proxies to backend on `127.0.0.1:8000`.
- Backend stack: Docker Compose services `ea-backend`, `ea-postgres`, and `ea-redis`.

## 2026-05-11 Deployment Notes

- Pushed and deployed production-readiness changes through GitHub.
- Created database backup before update: `backups/pre-update-20260511-132513.sql`.
- Existing PostgreSQL schema already matched the first Alembic schema, so the server database was baselined with `alembic stamp head`.
- Rotated default `EA_API_TOKEN` and `JWT_SECRET` in the server `.env`.
- Saved the pre-rotation environment backup as `.env.pre-secret-rotation-20260511-132837`.
- Read-only smoke test passed through both local backend URL and public IP.

## 2026-05-12 Command Lock Finding

Observed during production testing:

- Central system sent an `open_order` command to the MT5 EA.
- The EA side placed the order successfully.
- The command remained in `executing` in the central system.
- A following close command was rejected because the safety lock detected a previous unfinished trade command.

Root cause:

- The timeout scanner only expired `pending` and `received` commands.
- If the EA reported `executing` but its final `success`/`failed` result did not reach the server, the command could stay in `executing` indefinitely.

Fix:

- Include `executing` commands in timeout scanning.
- Once `expires_at` passes, stale `executing` commands become `timeout`, get a `command.timeout` audit log, and release the next trade command lock.
- Added a regression test for this flow in `backend/tests/test_api_smoke.py`.

Operational note:

- If this happens again, refresh the command list after the command timeout window. The stale command should become `timeout`, then the next close/open command can be submitted.
- If the command remains stuck beyond the timeout window after this fix is deployed, check EA journal logs for final result submission failures and verify the EA token configured in MT5.
