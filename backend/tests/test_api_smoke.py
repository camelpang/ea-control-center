"""Offline API smoke tests (no MT5, no market hours). Run from backend/: pytest tests -v."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ea_heartbeat_rejects_bad_token(client: TestClient) -> None:
    r = client.post(
        "/api/ea/heartbeat",
        headers={"X-EA-Token": "wrong"},
        json={"ea_id": "ea-1"},
    )
    assert r.status_code == 401


def test_weekend_command_loop_pause_and_result(client: TestClient) -> None:
    """Admin creates pause_trading; EA fetches and reports success — no trading session needed."""
    ea_tok = "test_ea_token"
    adm_tok = "test_admin_token"
    ea_id = "pytest-ea-001"

    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": ea_tok},
            json={
                "ea_id": ea_id,
                "terminal": "MT5",
                "status": "online",
                "allow_trading": True,
            },
        ).status_code
        == 200
    )

    c_resp = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": adm_tok},
        json={
            "ea_id": ea_id,
            "command_type": "pause_trading",
            "payload": {"reason": "pytest weekend"},
            "requested_by": "pytest",
        },
    )
    assert c_resp.status_code in (200, 201)
    cmd = c_resp.json()
    assert cmd["status"] == "pending"
    cmd_id = cmd["id"]

    poll = client.get(
        f"/api/ea/commands?ea_id={ea_id}",
        headers={"X-EA-Token": ea_tok},
    )
    assert poll.status_code == 200
    fetched = poll.json()
    assert len(fetched) >= 1
    assert any(x["id"] == cmd_id and x["status"] == "received" for x in fetched)

    fin = client.post(
        f"/api/ea/commands/{cmd_id}/result",
        headers={"X-EA-Token": ea_tok},
        json={"status": "success", "message": "trading paused", "raw": {"ok": True}},
    )
    assert fin.status_code == 200
    assert fin.json()["status"] == "success"

    logs = client.get("/api/admin/audit-logs?limit=20", headers={"X-Admin-Token": adm_tok})
    assert logs.status_code == 200
    result_logs = [
        row
        for row in logs.json()
        if row["action"] == "command.result" and row["details"]["command_id"] == cmd_id
    ]
    assert result_logs
    assert result_logs[0]["actor"] == f"ea:{ea_id}"
    assert result_logs[0]["details"]["status"] == "success"


def test_dashboard_eas_ok(client: TestClient) -> None:
    r = client.get("/api/admin/dashboard/eas", headers={"X-Admin-Token": "test_admin_token"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for row in body:
        assert "ea_id" in row
        assert "snapshot_profit" in row


def test_admin_can_create_user_and_assignment(client: TestClient) -> None:
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": "pytest-assigned-ea", "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    user = client.post(
        "/api/admin/users",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"username": "pytest-user", "password": "secret123", "role": "viewer"},
    )
    assert user.status_code == 201
    assert user.json()["username"] == "pytest-user"

    assignment = client.post(
        "/api/admin/assignments",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"username": "pytest-user", "ea_id": "pytest-assigned-ea", "can_view": True, "can_trade": True},
    )
    assert assignment.status_code == 201
    assert assignment.json()["ea_id"] == "pytest-assigned-ea"

    rows = client.get("/api/admin/assignments", headers={"X-Admin-Token": "test_admin_token"})
    assert rows.status_code == 200
    assert any(row["username"] == "pytest-user" for row in rows.json())


def test_viewer_can_read_own_assignments(client: TestClient) -> None:
    ea_id = "pytest-my-assignment-ea"
    username = "pytest-my-assignment-user"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/admin/users",
            headers={"X-Admin-Token": "test_admin_token"},
            json={"username": username, "password": "secret123", "role": "viewer"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/admin/assignments",
            headers={"X-Admin-Token": "test_admin_token"},
            json={"username": username, "ea_id": ea_id, "can_view": True, "can_trade": False},
        ).status_code
        == 201
    )
    login = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    own = client.get("/api/admin/my-assignments", headers={"Authorization": f"Bearer {token}"})
    assert own.status_code == 200
    body = own.json()
    assert len(body) == 1
    assert body[0]["ea_id"] == ea_id
    assert body[0]["can_trade"] is False

    all_rows = client.get("/api/admin/assignments", headers={"Authorization": f"Bearer {token}"})
    assert all_rows.status_code == 403


def test_admin_can_update_user_and_assignment(client: TestClient) -> None:
    ea_id = "pytest-update-assignment-ea"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/admin/users",
            headers={"X-Admin-Token": "test_admin_token"},
            json={"username": "pytest-edit-user", "password": "secret123", "role": "viewer"},
        ).status_code
        == 201
    )
    assignment = client.post(
        "/api/admin/assignments",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"username": "pytest-edit-user", "ea_id": ea_id, "can_view": True, "can_trade": False},
    )
    assert assignment.status_code == 201
    assignment_id = assignment.json()["id"]

    updated = client.patch(
        f"/api/admin/assignments/{assignment_id}",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"can_view": True, "can_trade": True, "is_primary_operator": True},
    )
    assert updated.status_code == 200
    assert updated.json()["can_trade"] is True
    assert updated.json()["is_primary_operator"] is True

    disabled = client.patch(
        "/api/admin/users/pytest-edit-user",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False


def test_primary_operator_update_conflict(client: TestClient) -> None:
    ea_id = "pytest-primary-conflict-ea"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    for username in ["pytest-primary-a", "pytest-primary-b"]:
        assert (
            client.post(
                "/api/admin/users",
                headers={"X-Admin-Token": "test_admin_token"},
                json={"username": username, "password": "secret123", "role": "viewer"},
            ).status_code
            == 201
        )
    first = client.post(
        "/api/admin/assignments",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"username": "pytest-primary-a", "ea_id": ea_id, "can_view": True, "is_primary_operator": True},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/admin/assignments",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"username": "pytest-primary-b", "ea_id": ea_id, "can_view": True},
    )
    assert second.status_code == 201
    conflict = client.patch(
        f"/api/admin/assignments/{second.json()['id']}",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"is_primary_operator": True},
    )
    assert conflict.status_code == 409


def test_admin_can_delete_unused_user(client: TestClient) -> None:
    username = "pytest-delete-unused-user"
    created = client.post(
        "/api/admin/users",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"username": username, "password": "secret123", "role": "viewer"},
    )
    assert created.status_code == 201

    deleted = client.delete(f"/api/admin/users/{username}", headers={"X-Admin-Token": "test_admin_token"})
    assert deleted.status_code == 200
    assert "deleted" in deleted.json()["message"]

    rows = client.get("/api/admin/users", headers={"X-Admin-Token": "test_admin_token"})
    assert rows.status_code == 200
    assert all(row["username"] != username for row in rows.json())


def test_admin_cannot_delete_user_with_assignment_history(client: TestClient) -> None:
    username = "pytest-delete-assigned-user"
    ea_id = "pytest-delete-assigned-ea"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/admin/users",
            headers={"X-Admin-Token": "test_admin_token"},
            json={"username": username, "password": "secret123", "role": "viewer"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/admin/assignments",
            headers={"X-Admin-Token": "test_admin_token"},
            json={"username": username, "ea_id": ea_id, "can_view": True},
        ).status_code
        == 201
    )

    blocked = client.delete(f"/api/admin/users/{username}", headers={"X-Admin-Token": "test_admin_token"})
    assert blocked.status_code == 409
    assert "assignment history" in blocked.text


def test_admin_can_create_ea_account(client: TestClient) -> None:
    r = client.post(
        "/api/admin/eas",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": "pytest-manual-ea-001",
            "account_number": "100200300",
            "broker": "Pytest Broker",
            "terminal": "MT5",
            "strategy_name": "manual-added",
            "version": "test",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["ea_id"] == "pytest-manual-ea-001"
    assert body["account_number"] == "100200300"

    rows = client.get("/api/admin/eas", headers={"X-Admin-Token": "test_admin_token"})
    assert rows.status_code == 200
    assert any(row["ea_id"] == "pytest-manual-ea-001" for row in rows.json())


def test_invalid_ea_id_is_rejected(client: TestClient) -> None:
    bad_manual = client.post(
        "/api/admin/eas",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"ea_id": "中文 EA", "terminal": "MT5"},
    )
    assert bad_manual.status_code == 422

    bad_heartbeat = client.post(
        "/api/ea/heartbeat",
        headers={"X-EA-Token": "test_ea_token"},
        json={"ea_id": "bad ea id", "terminal": "MT5", "status": "online"},
    )
    assert bad_heartbeat.status_code == 422


def test_admin_actions_create_audit_logs(client: TestClient) -> None:
    ea_id = "pytest-audit-ea-001"
    created = client.post(
        "/api/admin/eas",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"ea_id": ea_id, "terminal": "MT5", "account_number": "90001"},
    )
    assert created.status_code == 201

    logs = client.get("/api/admin/audit-logs", headers={"X-Admin-Token": "test_admin_token"})
    assert logs.status_code == 200
    body = logs.json()
    assert any(row["action"] == "ea.created" and row["resource_id"] == ea_id for row in body)


def test_ea_specific_token_is_accepted_for_matching_ea(client: TestClient) -> None:
    ea_id = "pytest-token-ea-001"
    token = "ea-specific-secret-001"
    created = client.post(
        "/api/admin/eas",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"ea_id": ea_id, "terminal": "MT5", "api_token": token},
    )
    assert created.status_code == 201
    assert created.json()["has_ea_token"] is True

    accepted = client.post(
        "/api/ea/heartbeat",
        headers={"X-EA-Token": token},
        json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
    )
    assert accepted.status_code == 200

    rejected = client.post(
        "/api/ea/heartbeat",
        headers={"X-EA-Token": token},
        json={"ea_id": "pytest-token-other-ea", "terminal": "MT5", "status": "online"},
    )
    assert rejected.status_code == 401


def test_admin_can_rotate_ea_token(client: TestClient) -> None:
    ea_id = "pytest-rotate-token-ea"
    assert (
        client.post(
            "/api/admin/eas",
            headers={"X-Admin-Token": "test_admin_token"},
            json={"ea_id": ea_id, "terminal": "MT5"},
        ).status_code
        == 201
    )
    rotated = client.post(f"/api/admin/eas/{ea_id}/token", headers={"X-Admin-Token": "test_admin_token"})
    assert rotated.status_code == 200
    body = rotated.json()
    assert body["ea_id"] == ea_id
    assert body["api_token"].startswith("ea_")

    heartbeat = client.post(
        "/api/ea/heartbeat",
        headers={"X-EA-Token": body["api_token"]},
        json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
    )
    assert heartbeat.status_code == 200


def test_active_command_blocks_second_trading_command(client: TestClient) -> None:
    ea_id = "pytest-command-lock-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    first = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"ea_id": ea_id, "command_type": "pause_trading", "payload": {}},
    )
    assert first.status_code == 201
    second = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={"ea_id": ea_id, "command_type": "close_all", "payload": {}},
    )
    assert second.status_code == 409


def test_cancel_order_command_type_accepted(client: TestClient) -> None:
    ea_id = "pytest-cancel-order-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    r = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "cancel_order",
            "payload": {"ticket": "123456789"},
            "requested_by": "pytest",
        },
    )
    assert r.status_code == 201
    assert r.json()["command_type"] == "cancel_order"


def test_open_order_payload_validation_rejects_invalid_volume(client: TestClient) -> None:
    ea_id = "pytest-open-validation-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    r = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "open_order",
            "payload": {"symbol": "XAUUSD", "side": "buy", "volume": 0},
        },
    )
    assert r.status_code == 422
    assert "建仓手数" in r.text


def test_pending_order_payload_validation_rejects_side_type_mismatch(client: TestClient) -> None:
    ea_id = "pytest-pending-validation-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    r = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "open_order",
            "payload": {
                "symbol": "XAUUSD",
                "side": "buy",
                "volume": 0.1,
                "order_mode": "pending",
                "pending_order": True,
                "order_type": "sell_limit",
                "price": 2500,
            },
        },
    )
    assert r.status_code == 422
    assert "买卖方向和挂单类型不一致" in r.text


def test_command_audit_log_includes_payload_summary(client: TestClient) -> None:
    ea_id = "pytest-audit-payload-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    r = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "open_order",
            "payload": {"symbol": "XAUUSD", "side": "buy", "volume": 0.1, "source": "pytest"},
            "requested_by": "pytest",
        },
    )
    assert r.status_code == 201
    logs = client.get("/api/admin/audit-logs?limit=20", headers={"X-Admin-Token": "test_admin_token"})
    assert logs.status_code == 200
    created = [row for row in logs.json() if row["action"] == "command.created" and row["resource_id"] == ea_id]
    assert created
    assert created[0]["details"]["payload_summary"]["symbol"] == "XAUUSD"


def test_timed_out_command_creates_audit_log(client: TestClient) -> None:
    ea_id = "pytest-timeout-audit-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    created = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "pause_trading",
            "payload": {"reason": "pytest timeout"},
            "expires_at": expired_at,
        },
    )
    assert created.status_code == 201
    command_id = created.json()["id"]

    rows = client.get("/api/admin/commands", headers={"X-Admin-Token": "test_admin_token"})
    assert rows.status_code == 200
    command = next(row for row in rows.json() if row["id"] == command_id)
    assert command["status"] == "timeout"

    logs = client.get("/api/admin/audit-logs?limit=20", headers={"X-Admin-Token": "test_admin_token"})
    assert logs.status_code == 200
    timeout_logs = [
        row
        for row in logs.json()
        if row["action"] == "command.timeout" and row["details"]["command_id"] == command_id
    ]
    assert timeout_logs
    assert timeout_logs[0]["actor"] == "system"
    assert timeout_logs[0]["details"]["ea_id"] == ea_id


def test_executing_command_can_timeout_and_unlock_next_trade(client: TestClient) -> None:
    ea_id = "pytest-executing-timeout-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )

    created = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "open_order",
            "payload": {"symbol": "XAUUSD", "side": "buy", "volume": 0.1, "source": "pytest"},
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
        },
    )
    assert created.status_code == 201
    command_id = created.json()["id"]

    fetched = client.get(
        f"/api/ea/commands?ea_id={ea_id}",
        headers={"X-EA-Token": "test_ea_token"},
    )
    assert fetched.status_code == 200
    assert fetched.json()[0]["id"] == command_id

    executing = client.post(
        f"/api/ea/commands/{command_id}/result",
        headers={"X-EA-Token": "test_ea_token"},
        json={"status": "executing", "message": "command started", "raw": {"source": "pytest"}},
    )
    assert executing.status_code == 200
    assert executing.json()["status"] == "executing"

    from app.database import SessionLocal
    from app.models import Command

    with SessionLocal() as db:
        command = db.get(Command, command_id)
        assert command is not None
        command.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()

    rows = client.get("/api/admin/commands", headers={"X-Admin-Token": "test_admin_token"})
    assert rows.status_code == 200
    command = next(row for row in rows.json() if row["id"] == command_id)
    assert command["status"] == "timeout"

    next_trade = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "close_all",
            "payload": {"source": "pytest"},
        },
    )
    assert next_trade.status_code == 201


def test_manual_manage_command_type_accepted(client: TestClient) -> None:
    ea_id = "pytest-manual-manage-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    r = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "manual_manage",
            "payload": {"manual_trade": True, "manual_manage": True},
            "requested_by": "pytest",
        },
    )
    assert r.status_code == 201
    assert r.json()["command_type"] == "manual_manage"


def test_manual_release_command_type_accepted(client: TestClient) -> None:
    ea_id = "pytest-manual-release-001"
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": ea_id, "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    r = client.post(
        "/api/admin/commands",
        headers={"X-Admin-Token": "test_admin_token"},
        json={
            "ea_id": ea_id,
            "command_type": "manual_release",
            "payload": {"manual_release": True},
            "requested_by": "pytest",
        },
    )
    assert r.status_code == 201
    assert r.json()["command_type"] == "manual_release"


def test_dashboard_eas_demo_count(client: TestClient) -> None:
    r = client.get(
        "/api/admin/dashboard/eas?demo=30",
        headers={"X-Admin-Token": "test_admin_token"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 30
    assert body[0]["ea_id"].startswith("v-ea-")


def test_dashboard_preview_count(client: TestClient) -> None:
    r = client.get("/api/dashboard-preview?count=30")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 30
    assert "ea_id" in body[0]


def test_dashboard_html_route(client: TestClient) -> None:
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "/ea-detail?ea=" in r.text
    assert "apiErrorMessage" in r.text
    assert "loadPermissionContext" in r.text
    assert "canTradeEa" in r.text
    assert "permissionTextForEa" in r.text
    assert "/api/admin/my-assignments" in r.text
    assert "confirmModal" in r.text
    assert "openConfirmDialog" in r.text
    assert "formatPayloadSummary" in r.text
    assert "window.confirm" not in r.text
    assert 'id="bulkSymbol" class="input" type="text" value="XAUUSD"' in r.text


def test_admin_html_route_is_global_overview(client: TestClient) -> None:
    r = client.get("/admin")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "全局状态" in r.text
    assert "风险轮廓" in r.text
    assert "交易安全配置" in r.text
    assert "系统自检" in r.text
    assert "功能入口" in r.text
    assert "risk-grid" in r.text
    assert "config-grid" in r.text
    assert "quick-link-grid" in r.text
    assert "globalActiveCommands" in r.text
    assert "safetyMaxVolume" in r.text
    assert "systemCheckStatus" in r.text
    assert "systemCheckList" in r.text
    assert "apiErrorMessage" in r.text
    assert "/api/admin/safety-config" in r.text
    assert "/api/admin/system-checks" in r.text
    assert "offlineRiskList" in r.text
    assert "activeCommandRiskList" in r.text
    assert "renderGlobalRisks" in r.text
    assert "loadGlobalCommands" in r.text
    assert "/ea-detail?ea=" in r.text
    assert 'href="/manual-trades?status=all"' in r.text
    assert 'href="/manual-trades?status=online"' in r.text
    assert 'href="/manual-trades?status=offline"' in r.text
    assert 'href="/manual-trades?risk=paused"' in r.text
    assert 'href="/manual-trades?commands=active"' in r.text
    assert 'href="/commands"' in r.text
    assert 'href="/audit-logs"' in r.text
    assert "hidden-legacy" in r.text
    assert "auditLogFeed" in r.text
    assert "/api/admin/audit-logs" in r.text


def test_system_checks_requires_admin(client: TestClient) -> None:
    r = client.get("/api/admin/system-checks")
    assert r.status_code in {401, 403}


def test_admin_can_read_system_checks(client: TestClient) -> None:
    r = client.get("/api/admin/system-checks", headers={"X-Admin-Token": "test_admin_token"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "warning", "error"}
    checks = {row["key"]: row for row in body["checks"]}
    assert checks["database"]["status"] == "ok"
    assert checks["allowed_trade_symbols"]["status"] == "ok"
    assert "XAUUSD" in checks["allowed_trade_symbols"]["message"]
    assert checks["admin_api_token"]["status"] == "warning"
    assert checks["ea_api_token"]["status"] == "warning"
    assert checks["jwt_secret"]["status"] == "warning"
    assert "test_admin_token" not in r.text
    assert "test_ea_token" not in r.text


def test_safety_config_requires_admin(client: TestClient) -> None:
    r = client.get("/api/admin/safety-config")
    assert r.status_code in {401, 403}


def test_admin_can_read_safety_config(client: TestClient) -> None:
    r = client.get("/api/admin/safety-config", headers={"X-Admin-Token": "test_admin_token"})
    assert r.status_code == 200
    body = r.json()
    assert body["max_manual_order_volume"] > 0
    assert body["allowed_trade_symbols"] == ["XAUUSD"]
    assert body["command_timeout_seconds"] > 0
    assert body["ea_offline_seconds"] > 0
    assert isinstance(body["public_dashboard_preview_enabled"], bool)
    assert body["notes"]


def test_commands_html_route(client: TestClient) -> None:
    r = client.get("/commands")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "命令历史" in r.text
    assert "commandsTableBody" in r.text
    assert "/api/admin/commands" in r.text
    assert "data-cancel-command-id" in r.text
    assert "eaSearchInput" in r.text
    assert "statusFilter" in r.text
    assert "typeFilter" in r.text
    assert "activeOnlyToggle" in r.text
    assert "exportCsvBtn" in r.text
    assert "clearFiltersBtn" in r.text
    assert "exportCommandsCsv" in r.text
    assert "commands-" in r.text
    assert "filteredCommands" in r.text
    assert "renderFilteredCommands" in r.text
    assert "clearFilters" in r.text
    assert "data-toggle-payload-id" in r.text
    assert "expandedPayloadIds" in r.text
    assert "renderPayloadRow" in r.text
    assert "renderStatusFlow" in r.text
    assert "renderLifecycle" in r.text
    assert "commandDuration" in r.text
    assert "loadPermissionContext" in r.text
    assert "canTradeCommand" in r.text
    assert "/api/admin/my-assignments" in r.text
    assert "lifecycle-meta" in r.text
    assert "status-flow" in r.text
    assert "apiErrorMessage" in r.text
    assert "命令参数 Payload" in r.text
    assert "<th>Payload</th>" not in r.text
    assert "/ea-detail?ea=" in r.text


def test_audit_logs_html_route(client: TestClient) -> None:
    r = client.get("/audit-logs")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "审计日志" in r.text
    assert "auditLogFeed" in r.text
    assert "auditSearchInput" in r.text
    assert "actionFilter" in r.text
    assert "actorFilter" in r.text
    assert "exportCsvBtn" in r.text
    assert "clearFiltersBtn" in r.text
    assert "exportAuditLogsCsv" in r.text
    assert "audit-logs-" in r.text
    assert "filteredAuditLogs" in r.text
    assert "renderFilteredAuditLogs" in r.text
    assert "apiErrorMessage" in r.text
    assert "/api/admin/audit-logs" in r.text


def test_ea_detail_html_route(client: TestClient) -> None:
    r = client.get("/ea-detail?ea=pytest-ea")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "EA 详情" in r.text
    assert "summaryStatus" in r.text
    assert "positionsTableBody" in r.text
    assert "snapshotsTableBody" in r.text
    assert "commandsList" in r.text
    assert "EA 操作" in r.text
    assert "data-safe-command" in r.text
    assert "交易操作" in r.text
    assert "tradeOperation" in r.text
    assert "sendTradeCommandBtn" in r.text
    assert "open_pending" in r.text
    assert "close_ticket" in r.text
    assert "commandTypeForOperation" in r.text
    assert "formatPayloadSummary" in r.text
    assert "activeCommandList" in r.text
    assert "conflictWarningsFor" in r.text
    assert "commandDuration" in r.text
    assert "耗时" in r.text
    assert "validateStopLossTakeProfit" in r.text
    assert "tradeSafetyNote" in r.text
    assert "validatePayloadAgainstSafety" in r.text
    assert "operationButtons" in r.text
    assert "currentAssignment" in r.text
    assert "setOperationControlsEnabled" in r.text
    assert "/api/admin/my-assignments" in r.text
    assert 'id="opSymbol" class="input" type="text" value="XAUUSD"' in r.text
    assert "apiErrorMessage" in r.text
    assert "/api/admin/safety-config" in r.text
    assert "人工管理规则" in r.text
    assert "permissionNote" in r.text
    assert "/api/auth/me" in r.text
    assert "activeCommandCount" in r.text
    assert "openConfirmDialog" in r.text
    assert "待领取 / 已领取 / 执行中命令" in r.text
    assert "/api/admin/eas/" in r.text
    assert "/api/admin/commands?ea_id=" in r.text
    assert "/api/admin/commands" in r.text


def test_manual_trades_html_route(client: TestClient) -> None:
    r = client.get("/manual-trades")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "人工建仓" in r.text
    assert "urlFilter" in r.text
    assert "hasUrlFilter" in r.text
    assert "urlFilterBanner" in r.text
    assert "data-summary-filter" in r.text
    assert "summaryFilterBanner" in r.text
    assert "summaryFilterLabel" in r.text
    assert "允许人工 EA" in r.text
    assert "冲突命令" in r.text
    assert "activeCommandsFor" in r.text
    assert "buildConfirmPreview" in r.text
    assert "confirmModal" in r.text
    assert "apiErrorMessage" in r.text
    assert "loadPermissionContext" in r.text
    assert "canTradeRow" in r.text
    assert "permissionTextForRow" in r.text
    assert "/api/admin/my-assignments" in r.text
    assert '<option value="3000">3 秒</option>' in r.text
    assert "onlineStatusText" in r.text
    assert "enrichRowsWithPositions" in r.text
    assert "/positions" in r.text
    assert "matchingPositionForRow" in r.text
    assert "当前持仓" in r.text
    assert "持仓中" in r.text
    assert 'id="opSymbol" class="input" type="text" value="XAUUSD"' in r.text
    assert "openConfirmDialog" in r.text
    assert "shouldShowParameterSummary" in r.text
    assert "formatPayloadSummary" in r.text
    assert "待领取 / 已领取 / 执行中命令" in r.text
    assert "离线 EA 提示" in r.text
    assert "window.confirm" not in r.text
    assert "/ea-detail?ea=" in r.text


def test_ea_accounts_html_route(client: TestClient) -> None:
    r = client.get("/ea-accounts")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "EA 账号列表" in r.text
    assert "assignmentFilter" in r.text
    assert "statusFilter" in r.text
    assert "tokenFilter" in r.text
    assert "pageSizeSelect" in r.text
    assert "pagedEas" in r.text
    assert "pageInfo" in r.text
    assert "data-save-ea" in r.text
    assert "bulkAssignBtn" in r.text
    assert "exportCsvBtn" in r.text
    assert "exportEasCsv" in r.text
    assert "ea-accounts-" in r.text
    assert "assignmentSummaryForEa" in r.text
    assert "tokenModal" in r.text
    assert "confirmTokenRotation" in r.text
    assert "copyGeneratedToken" in r.text
    assert "data-ea-select" in r.text
    assert "bulkSelectedEaList" in r.text
    assert "bulkExistingAssignments" in r.text
    assert "apiErrorDetail" in r.text
    assert "apiErrorMessage" in r.text
    assert "/users?user=" in r.text
    assert "initialEaFromUrl" in r.text
    assert "applyInitialEaFilter" in r.text
    assert "clearEaFiltersBtn" in r.text
    assert "clearEaFilters" in r.text
    assert "generateEaIdBtn" in r.text
    assert "generateEaId" in r.text
    assert "isValidEaId" in r.text
    assert "/ea-detail?ea=" in r.text
    assert "ea-form-grid" in r.text
    assert "策略 / 版本" not in r.text
    assert "data-ea-allow" not in r.text
    assert "window.confirm" not in r.text
    assert "window.prompt" not in r.text
    assert 'href="/users">分配' not in r.text
    assert "用户与分配" not in r.text


def test_users_html_route(client: TestClient) -> None:
    r = client.get("/users")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "用户列表" in r.text
    assert "user-form-grid" in r.text
    assert "创建 / 更新普通用户" in r.text
    assert "assignmentUserFilter" in r.text
    assert "assignmentEaFilter" in r.text
    assert "userPageSizeSelect" in r.text
    assert "pagedUsers" in r.text
    assert "userPageInfo" in r.text
    assert "exportUsersCsvBtn" in r.text
    assert "exportUsersCsv" in r.text
    assert "users-" in r.text
    assert "assignmentSummaryForUser" in r.text
    assert "permissionBadges" in r.text
    assert "data-edit-assignment" in r.text
    assert "data-view-user-assignments" in r.text
    assert "viewAssignmentsForUser" in r.text
    assert "initialUserFromUrl" in r.text
    assert "applyInitialUserFilter" in r.text
    assert "clearAssignmentFiltersBtn" in r.text
    assert "clearAssignmentFilters" in r.text
    assert "assignmentSection" in r.text
    assert "user-table" in r.text
    assert "actions-toolbar" in r.text
    assert "table-button" in r.text
    assert "apiErrorMessage" in r.text
    assert "data-delete-user" in r.text
    assert "/ea-accounts?ea=" in r.text
    assert "分配 EA 账号" not in r.text
    assert "assignBtn" not in r.text


def test_commands_limit_query(client: TestClient) -> None:
    r = client.get("/api/admin/commands?limit=500", headers={"X-Admin-Token": "test_admin_token"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_dashboard_preview_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.config as app_config

    monkeypatch.setattr(app_config.settings, "allow_public_dashboard_preview", False)
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        r = c.get("/api/dashboard-preview?count=5")
        assert r.status_code == 404
