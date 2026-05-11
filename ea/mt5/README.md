# MT5 EA Connector

This folder contains an MT5 Expert Advisor connector for the EA Control Center backend.

**MT4** uses the same HTTP/JSON endpoints; protocol-only notes are in [`../mt4/README.md`](../mt4/README.md).

## File

- `EAControlConnector.mq5`

## What It Does

- Sends heartbeat to `POST /api/ea/heartbeat`
- Sends account/position snapshot to `POST /api/ea/snapshot`
- Polls commands from `GET /api/ea/commands?ea_id=...`
- Submits execution result to `POST /api/ea/commands/{command_id}/result`

## Supported Commands

- `pause_trading`
- `resume_trading`
- `close_all`
- `close_symbol`
- `close_ticket`
- `cancel_order`
- `manual_manage`
- `manual_release`
- `open_order`
- `update_params`

Unsupported command types are returned as `failed` with message `unsupported command_type: ...`.

## Command Payload Examples

`close_symbol`

```json
{
  "symbol": "XAUUSD"
}
```

`close_ticket`

```json
{
  "ticket": "123456789"
}
```

`cancel_order`

```json
{
  "ticket": "123456789"
}
```

`manual_manage`

```json
{
  "manual_trade": true,
  "manual_manage": true,
  "reason": "added from dashboard"
}
```

`manual_release`

```json
{
  "manual_release": true,
  "reason": "removed from manual management page"
}
```

`open_order`

Market order:

```json
{
  "symbol": "XAUUSD",
  "side": "buy",
  "volume": 0.1,
  "sl": 3300.0,
  "tp": 3340.0,
  "comment": "opened-from-admin"
}
```

Pending order:

```json
{
  "symbol": "XAUUSD",
  "side": "buy",
  "volume": 0.1,
  "order_mode": "pending",
  "pending_order": true,
  "order_type": "buy_limit",
  "price": 3310.0,
  "sl": 3290.0,
  "tp": 3340.0,
  "comment": "pending-from-manual-trades"
}
```

`update_params`

```json
{
  "allow_trading": true,
  "heartbeat_interval_sec": 10,
  "snapshot_interval_sec": 15,
  "command_poll_interval_sec": 5
}
```

## MT5 Setup

1. Open MetaEditor, add `EAControlConnector.mq5` to `MQL5/Experts`.
2. Compile the file.
3. In MT5 terminal:
   - `Tools` -> `Options` -> `Expert Advisors`
   - Enable `Allow WebRequest for listed URL`
   - Add your API base URL, for example:
     - `http://47.86.170.144`
4. Attach the EA to a chart and set inputs:
   - `InpApiBaseUrl`
   - `InpEaToken`
   - `InpEaId` (optional; leave empty to auto-generate `mt5-{account}-{server}-{magic}`)
   - `InpTradeDeviationPoints`
   - `InpMagicNumber`

## Local Windows Integration

If MT5 and the backend are running on the same Windows machine, use:

```text
InpApiBaseUrl = http://127.0.0.1:8001
InpEaToken = ea123456
InpEaId =
```

When `InpEaId` is empty, the connector generates a stable ID from the MT5 account, server, and magic number. Set `InpEaId` manually only when you need a custom stable identifier.

Also add this WebRequest URL in MT5:

```text
http://127.0.0.1:8001
```

The local admin UI is:

```text
http://127.0.0.1:8001/admin
```

For the full local integration checklist, see:

```text
docs/mt5-local-integration.md
```

Before production testing, also follow:

```text
docs/mt5-production-checklist.md
```

## Notes

- `OnTick()` still only gates new trading by `g_allow_trading`; it does not contain your actual strategy logic yet.
- The connector now sends `executing` before the final `success` or `failed` result, which makes backend command logs easier to follow.
- Snapshot uploads include `swap`, `commission`, and extra `raw` metadata for easier troubleshooting.
- `update_params` updates runtime behavior only for the currently running EA instance; it does not permanently rewrite MT5 input parameters.
- EA IDs must be 3-128 characters and may only use letters, numbers, dot, underscore, hyphen, or colon.
- Backend trading safety defaults to `ALLOWED_TRADE_SYMBOLS=XAUUSD`; use the broker's exact gold symbol if it differs and update the backend whitelist accordingly.
- For MT5 broker suffixes, the connector can auto-map a backend symbol like `XAUUSD` to the current chart symbol such as `XAUUSD.c` for `open_order`, pending orders, and `close_symbol`. The command result message includes `mapped_symbol=XAUUSD->XAUUSD.c` when this happens.
- This chat environment cannot run MetaEditor, so the code was prepared for compilation and integration, but not compiled inside MT5 here.
