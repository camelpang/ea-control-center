# EA Account Retirement

Use EA account archiving when a trading account, terminal, broker demo, or test connector is no longer in active use but its history must remain available.

## Recommended Process

1. Confirm the EA has no open positions or pending orders in MT5.
2. Stop the connector or remove the EA from the chart if the account is permanently retired.
3. Open `EA 账号列表`, locate the EA, and click `归档`.
4. Enter a short reason, for example `demo account expired` or `broker migration completed`.
5. Verify the EA disappears from default monitoring and manual trading views.

## System Behavior

- Archived EA accounts keep snapshots, commands, assignments, and audit logs.
- Archived EA accounts are hidden from the default dashboard/manual trading screens.
- The backend rejects new trading commands for `archived` or `disabled` EA accounts.
- `恢复` returns an archived EA to `active`; trading still depends on `allow_trading` and user permissions.

## When Not To Archive

- Use `暂停 EA` when the account is still in service but strategy trading should pause temporarily.
- Keep the EA active when there are still live positions or pending orders that operators need to manage.
