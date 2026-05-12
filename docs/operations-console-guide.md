# Operations Console Guide

This guide explains how to use the main operation pages during production testing and daily review.

## Recommended Daily Flow

1. Open `/admin` for the global overview.
2. Open `/alerts` and clear critical or warning items first.
3. Open `/operator` to review assigned EAs, open orders, pending orders, and active commands.
4. Use `/manual-trades` for manual intervention, batch close, and pending-order cancellation.
5. Use `/commands` and `/audit-logs` to review what happened after every important action.
6. Use `/reports` at the end of the day or week for operational review.

## Main Pages

### `/admin` - Management Console

Use this as the central entry page.

It shows:

- global EA status
- risk overview
- safety configuration
- system self-checks
- quick links to every operation page

Recommended checks:

- `系统自检` must not show `error`.
- Production tokens and `JWT_SECRET` should not be default example values.
- `ALLOWED_TRADE_SYMBOLS` and `MAX_MANUAL_ORDER_VOLUME` should match the live testing policy.

### `/alerts` - Production Alert Center

Use this page first when something looks wrong.

Current alert types:

- EA offline
- stale snapshots
- failed or timed-out commands
- commands still pending, received, or executing
- trading permission disabled

Recommended handling:

- For offline EAs, check MT5 terminal status, WebRequest permission, EA token, and network access.
- For stale snapshots, confirm the EA is still sending snapshot payloads.
- For command failures, open `/commands` and inspect command logs.
- For stuck active commands, wait for timeout or cancel if still allowed.

### `/operator` - Operator Workbench

This is the focused daily page for operators.

Admins see all EAs. Viewer/operator users see only assigned EAs.

It shows:

- assigned EA count
- tradeable EA count
- offline EA count
- active commands
- current positions
- current pending orders
- recent alerts
- risk-sorted EA cards

Use the quick links on each EA card:

- `进入人工处理` goes to `/manual-trades?ea=<EA_ID>`
- `查看命令` goes to `/commands?ea_id=<EA_ID>`

### `/manual-trades` - Manual Trade Management

Use this page for controlled manual intervention.

Main uses:

- manual market entry
- pending-order entry
- close by symbol
- close by ticket
- cancel pending order
- batch close selected positions
- batch cancel selected pending orders
- pause and resume EA strategy trading

Important rules:

- The backend still validates all trade payloads.
- Archived or disabled EAs cannot receive new trading commands.
- The page uses latest snapshots for current positions and pending orders.
- Always check confirmation preview before sending batch actions.

### `/ea-accounts` - EA Account Management

Use this page to manage EA lifecycle and assignment.

Main uses:

- create or update EA metadata
- generate dedicated EA tokens
- assign EA access to users
- archive retired EA accounts
- restore archived EA accounts
- export EA account list as CSV

Archiving behavior:

- Archived EAs are hidden from default dashboard and manual trading views.
- Archived EAs keep command, snapshot, assignment, and audit history.
- Archived EAs cannot receive new trading commands.

See also:

```text
docs/ea-account-retirement.md
```

### `/commands` - Command History

Use this page to inspect command lifecycle and execution results.

Command states:

- `pending`
- `received`
- `executing`
- `success`
- `failed`
- `timeout`
- `cancelled`

Operational notes:

- Active trading-impact commands lock new trading-impact commands for the same EA.
- Commands can time out from `pending`, `received`, or `executing`.
- Admin cancellation is allowed only for cancellable non-final states.

### `/audit-logs` - Audit Logs

Use this page for accountability and incident review.

Common audit actions:

- `command.created`
- `command.result`
- `command.cancelled`
- `ea.archived`
- `ea.restored`
- `assignment.created`
- `assignment.updated`
- `assignment.revoked`
- `user.created`
- `user.updated`

Use filters and CSV export when preparing an incident or production test record.

### `/reports` - Reports And Review

Use this page for end-of-day or weekly review.

Current report sections:

- command totals
- success, failed, timeout, and active command counts
- manual intervention count
- command status distribution
- command type distribution
- operator distribution
- EA risk ranking
- archive and restore records

Recommended review questions:

- Which EAs had the most failures or timeouts?
- Which operations were repeated often?
- Did any operator need unexpected manual intervention?
- Were archived/restored accounts handled with a clear reason?
- Are there patterns that should become new safety rules?

## Backup And Restore

Before risky deployments or production tests:

```bash
scripts/backup-postgres.sh
```

Prove the backup can be restored into a temporary database:

```bash
scripts/restore-drill-postgres.sh backups/ea_control_YYYYmmdd_HHMMSS.sql
```

See:

```text
docs/backup-restore-drill.md
```

## Production Deployment References

Use these documents when preparing or updating a server:

```text
docs/production-readiness-checklist.md
docs/github-server-deploy.md
docs/operations-safety-model.md
docs/mt5-production-checklist.md
```

## Incident Review Checklist

When a production incident or unexpected trading operation happens:

1. Capture the EA ID, time range, and account number.
2. Open `/alerts` and record active alerts.
3. Open `/commands?ea_id=<EA_ID>` and inspect recent command logs.
4. Open `/audit-logs` and filter by actor, action, or EA ID.
5. Open `/reports` with a matching time window.
6. Confirm MT5 journal logs for the same period.
7. Record the root cause and any follow-up safety rule.

## Role Guidance

Admins:

- manage users and EA assignments
- rotate EA tokens
- archive or restore EA accounts
- view reports and audit logs
- adjust production configuration through `.env`

Operators:

- use `/operator` and `/manual-trades`
- operate only assigned EAs
- use `/commands` for assigned EA command history
- escalate token, assignment, archive, and global report questions to admins
