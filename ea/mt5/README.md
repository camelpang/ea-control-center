# MT5 EA Connector (MVP)

This folder contains a minimal MT5 Expert Advisor connector for the EA Control Center backend.

## File

- `EAControlConnector.mq5`

## What It Does

- Sends heartbeat to `POST /api/ea/heartbeat`
- Sends account/position snapshot to `POST /api/ea/snapshot`
- Polls commands from `GET /api/ea/commands?ea_id=...`
- Submits execution result to `POST /api/ea/commands/{command_id}/result`

## Supported Commands In This MVP

- `pause_trading`
- `resume_trading`
- `close_all`

Other command types are returned as `failed` with message `unsupported command_type`.

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

## Notes

- This is a connector skeleton for integration testing, not a full strategy EA.
- `OnTick` currently only gates new trading by `g_allow_trading`.
- Extend `ExecuteCommand()` to support additional command types (`close_symbol`, `close_ticket`, `open_order`, `update_params`) as needed.
