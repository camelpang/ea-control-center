# MT5 Production Test Checklist

Use this checklist before connecting a real MT5 terminal to the production server.

## 1. Recompile The EA

Always compile the current source before production testing:

```text
ea/mt5/EAControlConnector.mq5
```

Do not assume an existing `EAControlConnector.ex5` is current. Rebuild it in MetaEditor, then copy the new compiled file into the MT5 `MQL5/Experts` directory if needed.

## 2. Server URL And WebRequest

In MT5:

1. Open `Tools` -> `Options` -> `Expert Advisors`.
2. Enable `Allow WebRequest for listed URL`.
3. Add the exact backend base URL.

Examples:

```text
https://your-domain.example
http://your-server-ip
```

The EA input `InpApiBaseUrl` must match the allowed WebRequest URL exactly. Do not include a trailing slash unless you also add the same trailing-slash URL in MT5.

## 3. EA Identity

Recommended:

```text
InpEaId =
```

When left empty, the connector generates:

```text
mt5-{account}-{server}-{magic}
```

Set `InpEaId` manually only if you need a stable custom ID. It must be unique per EA instance and must match the EA registered in `/ea-accounts` if you use a dedicated token.

## 4. Token Setup

For first connection, you can use the global production `EA_API_TOKEN`.

For live testing, prefer a dedicated EA token:

1. Open `/ea-accounts`.
2. Find or create the EA account.
3. Click `生成Token`.
4. Copy the token immediately.
5. Paste it into MT5 `InpEaToken`.
6. Restart or reattach the EA.

Important:

- Dedicated tokens are shown only once.
- If a dedicated token exists for an EA, that token only works with the matching `ea_id`.
- Do not use local default `ea123456` on the production server.

## 5. Gold Symbol Policy

The backend default is gold-only:

```text
ALLOWED_TRADE_SYMBOLS=XAUUSD
```

Before sending trade commands:

- Confirm the broker's exact gold symbol in Market Watch.
- If the broker uses a suffix such as `XAUUSDm` or `XAUUSD.a`, the MT5 connector can auto-map backend `XAUUSD` commands to the current chart symbol for `open_order`, pending orders, and `close_symbol`.
- For strict backend validation, either keep sending `XAUUSD` and rely on EA-side mapping, or add the exact broker symbol to `ALLOWED_TRADE_SYMBOLS` if operators will type the suffixed symbol in the UI.
- Restart/redeploy the backend after changing `.env`.
- Confirm `/admin` -> `交易安全配置` shows the intended symbol.

Command examples should use `XAUUSD` unless the backend whitelist is changed.

## 6. Safe Initial EA Inputs

Suggested first production-test inputs:

```text
InpApiBaseUrl = https://your-domain.example
InpEaToken = dedicated token from /ea-accounts
InpEaId =
InpRequestTimeoutMs = 5000
InpHeartbeatIntervalSec = 10
InpSnapshotIntervalSec = 15
InpCommandPollIntervalSec = 5
InpTradeDeviationPoints = 20
InpMagicNumber = 20260509
InpAllowTradingOnStart = false
```

Start with `InpAllowTradingOnStart=false` if you want heartbeat and snapshot verification before allowing trade commands.

## 7. First Connection Checks

After attaching the EA:

- MT5 Experts log shows connector initialized.
- No WebRequest permission errors.
- `/ea-accounts` shows the EA.
- `/admin` or `/dashboard` shows heartbeat as online.
- Snapshot fields update.
- Open positions appear if the account has positions.
- `/audit-logs` records command results after commands execute.

## 8. Command Test Order

Use this order for low-risk testing:

1. `update_params` with harmless interval changes.
2. `pause_trading`.
3. `resume_trading`.
4. `manual_manage` and `manual_release` markers.
5. `cancel_order` only against a known test pending order.
6. `close_ticket` only against a known tiny test position.
7. `open_order` only after confirming symbol whitelist, max volume, and account risk.

Avoid `close_all` until you have verified command routing, permissions, and target EA identity.

## 9. Known Behavior

- `manual_manage` and `manual_release` are marker acknowledgements in this connector. They do not change your strategy logic by themselves.
- `pause_trading` and `resume_trading` update the connector's `g_allow_trading` flag.
- `update_params` changes runtime values only for the current EA instance. It does not rewrite MT5 input parameters permanently.
- The connector submits `executing` before final `success` or `failed`, so command history should show a lifecycle.

## 10. Troubleshooting

`401 Invalid EA token`:

- Check `InpEaToken`.
- Check whether the EA has a dedicated token and whether `InpEaId` matches.
- Try global `EA_API_TOKEN` only for initial registration, then rotate to a dedicated token.

Commands stay `pending`:

- Confirm the EA is attached and timers are running.
- Check `InpCommandPollIntervalSec`.
- Check MT5 Experts log for `/api/ea/commands`.
- Confirm WebRequest URL is allowed.

EA appears as offline:

- Check heartbeat interval.
- Check server URL.
- Check firewall, reverse proxy, and HTTPS certificate.
- Check backend `/health`.
