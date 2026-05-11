"""Synthetic dashboard rows for layout / TV-wall preview (no real accounts)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.models import CommandStatus, CommandType, utc_now

_CMD_TYPES = [
    CommandType.pause_trading,
    CommandType.resume_trading,
    CommandType.close_all,
    CommandType.update_params,
    CommandType.open_order,
    CommandType.close_symbol,
]
_CMD_STATUSES = [
    CommandStatus.success,
    CommandStatus.pending,
    CommandStatus.failed,
    CommandStatus.timeout,
    CommandStatus.executing,
]


def build_demo_dashboard_rows(count: int) -> list[dict]:
    now = utc_now()
    terminals = ["MT5", "MT5", "MT5", "MT4"]
    rows: list[dict] = []
    for i in range(1, count + 1):
        seen = now - timedelta(seconds=i * 37)
        snap_t = now - timedelta(seconds=i * 41 + 12)
        bal = Decimal("10000") + Decimal(i * 253)
        flt = Decimal("-820") + Decimal(i * 47)
        eq = bal + flt
        margin = (eq * Decimal("0.082")).quantize(Decimal("0.01"))
        free_m = (eq * Decimal("0.86")).quantize(Decimal("0.01"))
        risk_cycle = i % 11
        if risk_cycle == 0:
            st, rlevel, rtext, allow = "offline", "high", "ea_offline", True
        elif risk_cycle == 3:
            st, rlevel, rtext, allow = "online", "paused", "trading_paused", False
        elif risk_cycle == 5:
            st, rlevel, rtext, allow = "online", "watch", "command_in_progress", True
        elif risk_cycle == 7:
            st, rlevel, rtext, allow = "online", "high", "recent_command_issue", True
        else:
            st, rlevel, rtext, allow = "online", "normal", "normal", True
        rows.append(
            {
                "ea_id": f"v-ea-{i:02d}",
                "account_number": str(8800000 + i),
                "broker": f"演示券商 {(i % 5) + 1:02d}",
                "terminal": terminals[i % len(terminals)],
                "strategy_name": "DemoStrategy",
                "version": f"EAConnector-0.{i % 9}.0",
                "status": st,
                "allow_trading": allow,
                "last_seen_at": seen,
                "updated_at": seen,
                "positions_count": (i * 3) % 17,
                "latest_snapshot_at": snap_t,
                "latest_command_status": _CMD_STATUSES[i % len(_CMD_STATUSES)],
                "latest_command_type": _CMD_TYPES[i % len(_CMD_TYPES)],
                "latest_command_at": snap_t,
                "risk_level": rlevel,
                "risk_text": rtext,
                "currency": "USD",
                "balance": bal,
                "equity": eq,
                "margin": margin,
                "free_margin": free_m,
                "margin_level": Decimal(str(450.5 + i * 11.3)).quantize(Decimal("0.01")),
                "snapshot_profit": flt,
            }
        )
    return rows
