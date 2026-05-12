from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import inspect, select, text

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.dashboard_demo import build_demo_dashboard_rows
from app.models import User, UserRole
from app.routers import admin, auth, ea
from app.security import hash_password


def _bootstrap_first_admin() -> None:
    if not settings.first_admin_bootstrap:
        return
    if not settings.first_admin_username or not settings.first_admin_password:
        return
    db = SessionLocal()
    try:
        exists = db.scalar(select(User).limit(1))
        if exists:
            return
        user = User(
            username=settings.first_admin_username,
            password_hash=hash_password(settings.first_admin_password),
            role=UserRole.admin,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


def _ensure_lightweight_schema_updates() -> None:
    """Small no-Alembic upgrades for local MVP databases created before new columns existed."""
    inspector = inspect(engine)
    if "ea_instances" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("ea_instances")}
    dialect = engine.dialect.name
    api_token_enabled_type = "BOOLEAN DEFAULT TRUE NOT NULL"
    if dialect == "sqlite":
        api_token_enabled_type = "BOOLEAN DEFAULT 1 NOT NULL"

    statements: list[str] = []
    if "api_token_hash" not in columns:
        statements.append("ALTER TABLE ea_instances ADD COLUMN api_token_hash VARCHAR(255)")
    if "api_token_enabled" not in columns:
        statements.append(f"ALTER TABLE ea_instances ADD COLUMN api_token_enabled {api_token_enabled_type}")

    if not statements:
        return
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    static_dir = Path(__file__).resolve().parent / "static"
    dash = static_dir / "dashboard.html"

    def _dash_response() -> FileResponse:
        if not dash.is_file():
            raise HTTPException(status_code=404, detail="dashboard.html missing from static/")
        return FileResponse(dash, media_type="text/html; charset=utf-8")

    @app.on_event("startup")
    def on_startup() -> None:
        Base.metadata.create_all(bind=engine)
        _ensure_lightweight_schema_updates()
        _bootstrap_first_admin()

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "status": "ok",
            "admin": "/admin",
            "dashboard": "/dashboard",
            "dashboard_demo_30": "/dashboard?demo=30",
            "operator": "/operator",
            "reports": "/reports",
            "manual_trades": "/manual-trades",
            "ea_detail": "/ea-detail?ea=EA_ID",
            "alerts": "/alerts",
            "commands": "/commands",
            "audit_logs": "/audit-logs",
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/dashboard-preview")
    def dashboard_preview(count: int = Query(30, ge=1, le=120)) -> list[dict]:
        """无需登录的虚拟 EA 列表，仅用于大屏排版；生产环境可设置 ALLOW_PUBLIC_DASHBOARD_PREVIEW=false 关闭。"""
        if not settings.allow_public_dashboard_preview:
            raise HTTPException(status_code=404, detail="Public dashboard preview disabled")
        return build_demo_dashboard_rows(count)

    @app.get("/dashboard", include_in_schema=False)
    def dashboard_ui() -> FileResponse:
        return _dash_response()

    @app.get("/dashboard/", include_in_schema=False)
    def dashboard_ui_slash() -> FileResponse:
        return _dash_response()

    @app.get("/monitor", include_in_schema=False)
    def monitor_ui() -> FileResponse:
        return _dash_response()

    @app.get("/admin", include_in_schema=False)
    def admin_ui() -> FileResponse:
        return FileResponse(static_dir / "admin.html", media_type="text/html; charset=utf-8")

    @app.get("/manual-trades", include_in_schema=False)
    def manual_trades_ui() -> FileResponse:
        return FileResponse(static_dir / "manual_trades.html", media_type="text/html; charset=utf-8")

    @app.get("/operator", include_in_schema=False)
    def operator_ui() -> FileResponse:
        return FileResponse(static_dir / "operator.html", media_type="text/html; charset=utf-8")

    @app.get("/ea-accounts", include_in_schema=False)
    def ea_accounts_ui() -> FileResponse:
        return FileResponse(static_dir / "ea_accounts.html", media_type="text/html; charset=utf-8")

    @app.get("/ea-detail", include_in_schema=False)
    def ea_detail_ui() -> FileResponse:
        return FileResponse(static_dir / "ea_detail.html", media_type="text/html; charset=utf-8")

    @app.get("/users", include_in_schema=False)
    def users_ui() -> FileResponse:
        return FileResponse(static_dir / "users.html", media_type="text/html; charset=utf-8")

    @app.get("/commands", include_in_schema=False)
    def commands_ui() -> FileResponse:
        return FileResponse(static_dir / "commands.html", media_type="text/html; charset=utf-8")

    @app.get("/alerts", include_in_schema=False)
    def alerts_ui() -> FileResponse:
        return FileResponse(static_dir / "alerts.html", media_type="text/html; charset=utf-8")

    @app.get("/reports", include_in_schema=False)
    def reports_ui() -> FileResponse:
        return FileResponse(static_dir / "reports.html", media_type="text/html; charset=utf-8")

    @app.get("/audit-logs", include_in_schema=False)
    def audit_logs_ui() -> FileResponse:
        return FileResponse(static_dir / "audit_logs.html", media_type="text/html; charset=utf-8")

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(ea.router, prefix="/api/ea", tags=["ea"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    return app


app = create_app()
