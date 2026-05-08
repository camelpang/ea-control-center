# MT5 EA Connector

This folder contains an MT5 Expert Advisor connector for the EA Control Center backend.

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
- `open_order`
- `update_params`

Unsupported command types are returned as `failed` with message `unsupported command_type: ...`.

## Command Payload Examples

`close_symbol`

```json
{
  "symbol": "EURUSD"
}
```

`close_ticket`

```json
{
  "ticket": "123456789"
}
```

`open_order`

```json
{
  "symbol": "EURUSD",
  "side": "buy",
  "volume": 0.1,
  "sl": 1.08,
  "tp": 1.09,
  "comment": "opened-from-admin"
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
   - `InpEaId`
   - `InpTradeDeviationPoints`
   - `InpMagicNumber`

## Notes

- `OnTick()` still only gates new trading by `g_allow_trading`; it does not contain your actual strategy logic yet.
- The connector now sends `executing` before the final `success` or `failed` result, which makes backend command logs easier to follow.
- Snapshot uploads include `swap`, `commission`, and extra `raw` metadata for easier troubleshooting.
- `update_params` updates runtime behavior only for the currently running EA instance; it does not permanently rewrite MT5 input parameters.
- This chat environment cannot run MetaEditor, so the code was prepared for compilation and integration, but not compiled inside MT5 here.
