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

## 2026-05-12 Manual Trades UI Follow-Up

Observed during production testing:

- Manual trades cards did not show online/offline status directly.
- Auto-refresh did not provide a `3 秒` option.
- The card `订单号` field stayed empty after a successful manual open order because the open command payload does not know the broker ticket before execution.

Fix:

- Added an online/offline/unknown status badge to every manual trades card.
- Added `3 秒` to the auto-refresh dropdown.
- The page now loads current positions from `/api/admin/eas/{ea_id}/positions` and uses the matched position `ticket` to fill the card order number and the default close-by-ticket value.

## 2026-05-12 Public Manual Management Visibility

Observed during public-IP testing:

- The public server showed the EA as online with an open position on the dashboard.
- The manual trades page did not show it when there was no matching manual/open command history on that server database.

Fix:

- The manual trades page now also includes EAs that currently have open positions, even if they do not yet have a manual-management command record.
- These rows are labeled as `当前持仓` / `持仓中` and can be selected for unified close/manual-management actions.

## 2026-05-12 EA Card Assignment Visibility

Observed during public-IP testing:

- Operators had to switch back to the EA account list to check which user owns or is assigned to an EA.

Fix:

- Dashboard EA cards now show `归属分配` from the existing `assigned_users` API field.
- Manual trades EA cards also show the same assignment summary, so operators can confirm ownership before sending close/manual commands.

## 2026-05-12 Production Enum Sync

Observed during public-IP testing:

- Creating a close-by-ticket command returned `500 Internal Server Error`.
- Backend logs showed PostgreSQL rejected `cancel_order` in the `command_type` enum during active-command lock checking.
- The production database enum still had the older command list: pause/resume/close/open/update only.

Fix:

- Added Alembic migration `20260512_0002_sync_command_type_enum.py`.
- The migration adds missing PostgreSQL enum values: `cancel_order`, `manual_manage`, and `manual_release`.
- After deployment, close-by-ticket and manual-management commands can be created without the enum mismatch.

## 2026-05-12 Pending Order Ticket Visibility

Observed during public-IP testing:

- A pending order was placed successfully, but the manual trades card could not show an order number.
- Pending orders are not open positions, so they do not appear in the snapshot `positions` list.
- The MT5 connector result message did not include the broker pending-order ticket, so the UI had nothing to use for `cancel_order`.

Fix:

- MT5 pending-order success messages now include `order_ticket=<ticket>` from `CTrade::ResultOrder()`.
- Manual trades cards now parse `ticket`, `order_ticket`, or `order=<number>` from command payloads and command result logs.
- Existing pending orders created before this EA update still require copying the ticket from the MT5 Trade tab.
