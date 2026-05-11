"""Auth / JWT smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def test_login_and_admin_with_jwt(client: TestClient) -> None:
    db = SessionLocal()
    try:
        db.add(User(username="adm1", password_hash=hash_password("secret123"), role=UserRole.admin))
        db.commit()
    finally:
        db.close()

    r = client.post("/api/auth/login", json={"username": "adm1", "password": "secret123"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body
    token = body["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "adm1"

    ea = client.get("/api/admin/eas", headers={"Authorization": f"Bearer {token}"})
    assert ea.status_code == 200


def test_viewer_only_sees_assigned_eas_and_trade_permission_is_enforced(client: TestClient) -> None:
    db = SessionLocal()
    try:
        db.add(User(username="adm2", password_hash=hash_password("adminpass"), role=UserRole.admin))
        db.add(User(username="view1", password_hash=hash_password("x"), role=UserRole.viewer))
        db.commit()
    finally:
        db.close()

    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": "assigned-ea", "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/ea/heartbeat",
            headers={"X-EA-Token": "test_ea_token"},
            json={"ea_id": "other-ea", "terminal": "MT5", "status": "online"},
        ).status_code
        == 200
    )

    admin_login = client.post("/api/auth/login", json={"username": "adm2", "password": "adminpass"})
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    assign = client.post(
        "/api/admin/assignments",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"username": "view1", "ea_id": "assigned-ea", "can_view": True, "can_trade": False},
    )
    assert assign.status_code == 201

    viewer_login = client.post("/api/auth/login", json={"username": "view1", "password": "x"})
    assert viewer_login.status_code == 200
    viewer_token = viewer_login.json()["access_token"]
    eas = client.get("/api/admin/eas", headers={"Authorization": f"Bearer {viewer_token}"})
    assert eas.status_code == 200
    assert [row["ea_id"] for row in eas.json()] == ["assigned-ea"]

    hidden_positions = client.get("/api/admin/eas/other-ea/positions", headers={"Authorization": f"Bearer {viewer_token}"})
    assert hidden_positions.status_code == 404

    no_trade = client.post(
        "/api/admin/commands",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"ea_id": "assigned-ea", "command_type": "pause_trading", "payload": {}},
    )
    assert no_trade.status_code == 403

    assign_trade = client.post(
        "/api/admin/assignments",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"username": "view1", "ea_id": "assigned-ea", "can_view": True, "can_trade": True},
    )
    assert assign_trade.status_code == 201
    can_trade = client.post(
        "/api/admin/commands",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"ea_id": "assigned-ea", "command_type": "pause_trading", "payload": {}},
    )
    assert can_trade.status_code == 201
