# MT5 Local Integration Guide

This guide describes the fastest way to connect the local backend and the MT5 EA on the same Windows machine.

## 1. Start the local backend

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-backend.ps1 -StopExisting
```

The script defaults to port `8001`, stops any old listener when `-StopExisting` is used, starts Uvicorn in the background, and waits for `/health` before it exits.

Useful variants:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-backend.ps1 -StopOnly
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-backend.ps1 -Foreground
```

Logs are written to `.local/backend-8001.out.log` and `.local/backend-8001.err.log`.

Local values currently used by this project:

```text
Admin UI:        http://127.0.0.1:8001/admin
EA API base URL: http://127.0.0.1:8001
EA_API_TOKEN:    ea123456
ADMIN_API_TOKEN: admin123456
```

## 2. Open the admin UI

In a browser:

```text
http://127.0.0.1:8001/admin
```

Use this admin token:

```text
admin123456
```

## 3. Configure MT5 WebRequest

In MT5:

1. `Tools` -> `Options` -> `Expert Advisors`
2. Enable `Allow WebRequest for listed URL`
3. Add:

```text
http://127.0.0.1:8001
```

If MT5 cannot access `127.0.0.1`, use your Windows LAN IP instead and update the EA input accordingly.

## 4. Configure EA inputs

Attach `EAControlConnector.mq5` to a chart and set:

```text
InpApiBaseUrl = http://127.0.0.1:8001
InpEaToken = ea123456
InpEaId = mt5-ea-001
InpRequestTimeoutMs = 5000
InpHeartbeatIntervalSec = 10
InpSnapshotIntervalSec = 15
InpCommandPollIntervalSec = 5
InpTradeDeviationPoints = 20
InpMagicNumber = 20260509
InpAllowTradingOnStart = true
```

## 5. Expected local integration flow

After the EA is attached successfully:

1. The admin page should show the EA from `offline` to `online`
2. Heartbeat time should update automatically
3. Snapshot data should appear in the snapshot panel
4. Positions should appear when the account has open trades
5. Commands sent from the admin page should move through:

```text
Pending -> Received -> Executing -> Success/Failed
```

## 6. Quick troubleshooting

### MT5 shows `401 Invalid EA token`

Check:

```text
InpEaToken = ea123456
```

### MT5 cannot send requests

Check:

- WebRequest URL is added exactly as `http://127.0.0.1:8001`
- Local backend is still running
- Windows firewall is not blocking MT5

### Admin page opens but no EA appears

Check MT5 Experts log for:

- heartbeat errors
- snapshot errors
- WebRequest permission errors

### Commands stay at `Pending`

That means the EA has not fetched them yet. Check:

- the EA is still running on the chart
- `InpApiBaseUrl` is correct
- command polling interval is not too large
- MT5 Experts log for `/api/ea/commands`
