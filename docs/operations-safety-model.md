# Operations Safety Model

This document records the current command and safety rules for the EA Control Center.

## Command Lifecycle

- Commands start as `pending`.
- The EA reports `executing` when it begins processing a command.
- Final states are `success`, `failed`, `timeout`, and `cancelled`.
- Admin cancellation is allowed only while a command is `pending` or `received`.
- Commands that pass `expires_at` while still `pending` or `received` are marked `timeout`.

## Per-EA Command Locking

Trading-impact commands are locked per EA while another trading-impact command is active.

Locked command types:

- `pause_trading`
- `resume_trading`
- `open_order`
- `close_all`
- `close_symbol`
- `close_ticket`
- `cancel_order`

An active command is any locked command in `pending`, `received`, or `executing`.

## Pause Versus Manual Commands

`pause_trading` means "pause automatic strategy trading." It is not a hard EA stop.

Expected EA behavior:

- Continue heartbeat.
- Continue snapshots.
- Continue command polling.
- Continue executing manual close/cancel commands.
- Stop strategy-driven automatic entries until `resume_trading`.

## Manual Management Rule

Manual management is treated as a derived operational state:

- Manual market or pending entries set `manual_trade=true` and `order_source=manual`.
- `/manual-trades` and `/ea-detail` use command history and payload markers to show manual intervention context.
- `resume_trading` is the normal operator action for leaving manual intervention after checks are complete.
- `manual_manage` / `manual_release` remain supported as low-level marker commands for compatibility and repair.

## Trading Safety Gates

The backend validates command payloads even if a user bypasses the UI.

- `open_order` requires `symbol`, `side`, and positive `volume`.
- `volume` must be less than or equal to `MAX_MANUAL_ORDER_VOLUME`.
- `ALLOWED_TRADE_SYMBOLS` defaults to `XAUUSD`; symbols outside the whitelist are rejected.
- Pending orders require positive `price`.
- Pending `side` must match `order_type`.
- Basic SL/TP direction checks are enforced.
- `close_symbol` requires `symbol`.
- `close_ticket` and `cancel_order` require `ticket`.
- `close_all.max_slippage_points` must be non-negative when provided.

## Permissions

- Admin users can view and operate all EAs.
- Viewer users can only view assigned EAs.
- Viewer users can only trade assigned EAs with `can_trade=true`.
- The backend is the final authority; UI hints are informational.

## Audit

Command creation logs include:

- actor and role
- EA ID
- command type
- requested_by
- a sanitized payload summary with key trading fields
