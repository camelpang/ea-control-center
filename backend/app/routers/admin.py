import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import get_db
from app.dashboard_demo import build_demo_dashboard_rows
from app.models import (
    AccountSnapshot,
    AuditLog,
    Command,
    CommandLog,
    CommandStatus,
    CommandType,
    EAInstance,
    EAUserAssignment,
    Position,
    User,
    UserRole,
    utc_now,
)
from app.schemas import (
    AccountSnapshotOut,
    AuditLogOut,
    CommandCreateIn,
    CommandOut,
    EAAssignmentIn,
    EAAssignmentOut,
    EAAssignmentUpdateIn,
    EACreateIn,
    EADashboardCardOut,
    EATokenOut,
    EAOut,
    MessageOut,
    PositionOut,
    SafetyConfigOut,
    SystemCheckOut,
    SystemCheckItemOut,
    UserCreateIn,
    UserUpdateIn,
    UserOut,
)
from app.security import AdminPrincipal, hash_password, require_console_access

router = APIRouter()


def require_admin_principal(principal: AdminPrincipal) -> None:
    if principal.role != UserRole.admin.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


def visible_ea_ids_stmt(principal: AdminPrincipal):
    if principal.role == UserRole.admin.value:
        return select(EAInstance.ea_id)
    return (
        select(EAUserAssignment.ea_id)
        .join(User, User.id == EAUserAssignment.user_id)
        .where(
            User.username == principal.subject,
            User.is_active.is_(True),
            EAUserAssignment.revoked_at.is_(None),
            EAUserAssignment.can_view.is_(True),
        )
    )


def assignment_display_users_by_ea(db: Session) -> dict[str, list[str]]:
    rows = db.execute(
        select(EAUserAssignment.ea_id, User.username)
        .join(User, User.id == EAUserAssignment.user_id)
        .where(
            EAUserAssignment.revoked_at.is_(None),
            or_(
                EAUserAssignment.can_view.is_(True),
                EAUserAssignment.can_trade.is_(True),
                EAUserAssignment.is_primary_operator.is_(True),
            ),
        )
        .order_by(EAUserAssignment.ea_id.asc(), User.username.asc())
    ).all()
    result: dict[str, list[str]] = {}
    for ea_id, username in rows:
        result.setdefault(ea_id, []).append(username)
    return result


def require_ea_access(
    db: Session,
    principal: AdminPrincipal,
    ea_id: str,
    *,
    trade: bool = False,
) -> EAInstance:
    ea = db.scalar(select(EAInstance).where(EAInstance.ea_id == ea_id))
    if ea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EA not found")
    if principal.role == UserRole.admin.value:
        return ea

    assignment = db.scalar(
        select(EAUserAssignment)
        .join(User, User.id == EAUserAssignment.user_id)
        .where(
            User.username == principal.subject,
            User.is_active.is_(True),
            EAUserAssignment.ea_id == ea_id,
            EAUserAssignment.revoked_at.is_(None),
            EAUserAssignment.can_view.is_(True),
        )
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EA not found")
    if trade and not assignment.can_trade:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="EA trade permission required")
    return ea


def _assignment_out(row: EAUserAssignment) -> dict:
    return {
        "id": row.id,
        "ea_id": row.ea_id,
        "username": row.user.username,
        "can_view": row.can_view,
        "can_trade": row.can_trade,
        "is_primary_operator": row.is_primary_operator,
        "assigned_by": row.assigned_by,
        "created_at": row.created_at,
        "revoked_at": row.revoked_at,
    }


def write_audit_log(
    db: Session,
    principal: AdminPrincipal,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor=principal.subject,
            actor_role=principal.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
    )


LOCKED_COMMAND_TYPES = {
    "pause_trading",
    "resume_trading",
    "close_all",
    "close_symbol",
    "close_ticket",
    "cancel_order",
    "open_order",
}


def _payload_number(payload: dict, key: str) -> float | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"参数 {key} 必须是数字")


def _require_payload_text(payload: dict, key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"缺少必填参数：{key}")
    return value


def _allowed_trade_symbols() -> set[str]:
    raw = settings.allowed_trade_symbols.strip()
    if not raw:
        return set()
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def _validate_trade_symbol(symbol: str) -> None:
    allowed = _allowed_trade_symbols()
    if allowed and symbol.upper() not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"交易品种不在白名单中：{symbol}；允许品种：{', '.join(sorted(allowed))}",
        )


def _validate_sl_tp(*, side: str, price: float | None, sl: float | None, tp: float | None, pending: bool) -> None:
    if sl is not None and tp is not None:
        if side == "buy" and sl >= tp:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="买入订单要求止损价小于止盈价")
        if side == "sell" and tp >= sl:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="卖出订单要求止盈价小于止损价")
    if pending and price is not None:
        if side == "buy":
            if sl is not None and sl >= price:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="买入挂单要求止损价小于挂单价格")
            if tp is not None and tp <= price:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="买入挂单要求止盈价大于挂单价格")
        if side == "sell":
            if sl is not None and sl <= price:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="卖出挂单要求止损价大于挂单价格")
            if tp is not None and tp >= price:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="卖出挂单要求止盈价小于挂单价格")


def validate_command_payload(payload: CommandCreateIn) -> dict:
    command_type = payload.command_type
    data = dict(payload.payload or {})

    if command_type == CommandType.open_order:
        symbol = _require_payload_text(data, "symbol")
        _validate_trade_symbol(symbol)
        side = str(data.get("side") or "").strip().lower()
        if side not in {"buy", "sell"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="买卖方向必须是 buy 或 sell")
        volume = _payload_number(data, "volume")
        if volume is None or volume <= 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="建仓手数必须大于 0")
        if volume > settings.max_manual_order_volume:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"建仓手数超过当前安全上限：{settings.max_manual_order_volume}",
            )
        order_mode = str(data.get("order_mode") or "").strip().lower()
        pending = bool(data.get("pending_order")) or order_mode == "pending"
        price = _payload_number(data, "price") if pending else None
        if pending:
            if price is None or price <= 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="挂单价格必须大于 0")
            order_type = str(data.get("order_type") or "buy_limit").strip().lower()
            if order_type not in {"buy_limit", "sell_limit", "buy_stop", "sell_stop"}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不支持的挂单类型")
            expected_side = "sell" if order_type.startswith("sell") else "buy"
            if side != expected_side:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="买卖方向和挂单类型不一致")
        _validate_sl_tp(
            side=side,
            price=price,
            sl=_payload_number(data, "sl"),
            tp=_payload_number(data, "tp"),
            pending=pending,
        )

    if command_type == CommandType.close_symbol:
        symbol = _require_payload_text(data, "symbol")
        _validate_trade_symbol(symbol)

    if command_type in {CommandType.close_ticket, CommandType.cancel_order}:
        _require_payload_text(data, "ticket")

    if command_type == CommandType.close_all:
        slippage = _payload_number(data, "max_slippage_points")
        if slippage is not None and slippage < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="最大滑点不能小于 0")

    return data


def command_payload_summary(payload: dict) -> dict:
    keys = [
        "symbol",
        "side",
        "volume",
        "order_mode",
        "order_type",
        "price",
        "ticket",
        "max_slippage_points",
        "manual_trade",
        "manual_manage",
        "manual_release",
        "source",
    ]
    return {key: payload[key] for key in keys if key in payload}


def ensure_no_active_locked_command(db: Session, ea_id: str, command_type: object) -> None:
    command_type_value = getattr(command_type, "value", str(command_type))
    if command_type_value not in LOCKED_COMMAND_TYPES:
        return
    locked_types = [CommandType(value) for value in LOCKED_COMMAND_TYPES]
    existing = db.scalar(
        select(Command)
        .where(
            Command.ea_id == ea_id,
            Command.status.in_([CommandStatus.pending, CommandStatus.received, CommandStatus.executing]),
            Command.command_type.in_(locked_types),
        )
        .order_by(desc(Command.created_at))
        .limit(1)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"EA 已有未完成交易命令 #{existing.id}；请等待完成后再下发新的交易命令",
        )


def mark_timed_out_commands(db: Session) -> None:
    now = utc_now()
    timed_out = list(
        db.scalars(
            select(Command).where(
                and_(
                    Command.status.in_([CommandStatus.pending, CommandStatus.received, CommandStatus.executing]),
                    Command.expires_at.is_not(None),
                    Command.expires_at <= now,
                )
            )
        )
    )
    for command in timed_out:
        command.status = CommandStatus.timeout
        command.completed_at = now
        command.logs.append(CommandLog(status=CommandStatus.timeout, message="Command expired before completion"))
        db.add(
            AuditLog(
                actor="system",
                actor_role="system",
                action="command.timeout",
                resource_type="command",
                resource_id=str(command.id),
                details={
                    "ea_id": command.ea_id,
                    "command_id": command.id,
                    "command_type": command.command_type.value,
                    "expires_at": command.expires_at.isoformat() if command.expires_at else None,
                },
            )
        )


def _latest_snapshots_by_ea_id(db: Session, principal: AdminPrincipal) -> dict[str, AccountSnapshot]:
    subq = (
        select(AccountSnapshot.ea_id, func.max(AccountSnapshot.id).label("mid"))
        .where(AccountSnapshot.ea_id.in_(visible_ea_ids_stmt(principal)))
        .group_by(AccountSnapshot.ea_id)
        .subquery()
    )
    rows = list(
        db.scalars(
            select(AccountSnapshot).join(
                subq,
                and_(AccountSnapshot.ea_id == subq.c.ea_id, AccountSnapshot.id == subq.c.mid),
            )
        ).all()
    )
    return {r.ea_id: r for r in rows}


@router.get("/dashboard/eas", response_model=list[EADashboardCardOut])
def dashboard_eas(
    demo: int | None = Query(None, ge=1, le=120),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[dict]:
    """所有 EA 的交易/资金概况；`demo=N` 时返回 N 条虚拟数据（需管理员鉴权），便于排版验收。"""
    if demo is not None:
        return build_demo_dashboard_rows(demo)

    now = utc_now()
    timeout_window = timedelta(seconds=settings.ea_offline_seconds)
    eas = list(
        db.scalars(
            select(EAInstance)
            .where(EAInstance.ea_id.in_(visible_ea_ids_stmt(principal)))
            .order_by(desc(EAInstance.last_seen_at))
        )
    )
    latest_snap = _latest_snapshots_by_ea_id(db, principal)

    position_counts = {
        ea_id: count
        for ea_id, count in db.execute(
            select(Position.ea_id, func.count(Position.id))
            .where(Position.ea_id.in_(visible_ea_ids_stmt(principal)))
            .group_by(Position.ea_id)
        ).all()
    }
    latest_snapshot_times = {
        ea_id: created_at
        for ea_id, created_at in db.execute(
            select(AccountSnapshot.ea_id, func.max(AccountSnapshot.created_at))
            .where(AccountSnapshot.ea_id.in_(visible_ea_ids_stmt(principal)))
            .group_by(AccountSnapshot.ea_id)
        ).all()
    }
    assigned_users_by_ea = assignment_display_users_by_ea(db) if principal.role == UserRole.admin.value else {}

    result: list[dict] = []
    for ea in eas:
        last_seen_at = ea.last_seen_at
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=now.tzinfo)
        status = ea.status
        if now - last_seen_at > timeout_window:
            status = "offline"

        latest_command = db.scalar(
            select(Command)
            .where(Command.ea_id == ea.ea_id, Command.ea_id.in_(visible_ea_ids_stmt(principal)))
            .order_by(desc(Command.created_at))
            .limit(1)
        )

        risk_level = "normal"
        risk_text = "normal"
        if status == "offline":
            risk_level = "high"
            risk_text = "ea_offline"
        elif latest_command and latest_command.status in {CommandStatus.failed, CommandStatus.timeout}:
            risk_level = "high"
            risk_text = "recent_command_issue"
        elif latest_command and latest_command.status in {CommandStatus.pending, CommandStatus.received, CommandStatus.executing}:
            risk_level = "watch"
            risk_text = "command_in_progress"
        elif not ea.allow_trading:
            risk_level = "paused"
            risk_text = "trading_paused"

        snap = latest_snap.get(ea.ea_id)
        row: dict = {
            "ea_id": ea.ea_id,
            "account_number": ea.account_number,
            "broker": ea.broker,
            "terminal": ea.terminal,
            "strategy_name": ea.strategy_name,
            "version": ea.version,
            "status": status,
            "allow_trading": ea.allow_trading,
            "last_seen_at": ea.last_seen_at,
            "updated_at": ea.updated_at,
            "positions_count": position_counts.get(ea.ea_id, 0),
            "latest_snapshot_at": latest_snapshot_times.get(ea.ea_id),
            "latest_command_status": latest_command.status if latest_command else None,
            "latest_command_type": latest_command.command_type if latest_command else None,
            "latest_command_at": latest_command.updated_at if latest_command else None,
            "risk_level": risk_level,
            "risk_text": risk_text,
            "assigned_users": assigned_users_by_ea.get(ea.ea_id, []),
            "currency": snap.currency if snap else None,
            "balance": snap.balance if snap else None,
            "equity": snap.equity if snap else None,
            "margin": snap.margin if snap else None,
            "free_margin": snap.free_margin if snap else None,
            "margin_level": snap.margin_level if snap else None,
            "snapshot_profit": snap.profit if snap else None,
        }
        result.append(row)
    return result


@router.get("/eas", response_model=list[EAOut])
def list_eas(
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[dict]:
    now = utc_now()
    timeout_window = timedelta(seconds=settings.ea_offline_seconds)
    eas = list(
        db.scalars(
            select(EAInstance)
            .where(EAInstance.ea_id.in_(visible_ea_ids_stmt(principal)))
            .order_by(desc(EAInstance.last_seen_at))
        )
    )

    position_counts = {
        ea_id: count
        for ea_id, count in db.execute(
            select(Position.ea_id, func.count(Position.id))
            .where(Position.ea_id.in_(visible_ea_ids_stmt(principal)))
            .group_by(Position.ea_id)
        ).all()
    }
    latest_snapshot_times = {
        ea_id: created_at
        for ea_id, created_at in db.execute(
            select(AccountSnapshot.ea_id, func.max(AccountSnapshot.created_at))
            .where(AccountSnapshot.ea_id.in_(visible_ea_ids_stmt(principal)))
            .group_by(AccountSnapshot.ea_id)
        ).all()
    }
    assigned_users_by_ea = assignment_display_users_by_ea(db) if principal.role == UserRole.admin.value else {}

    result: list[dict] = []
    for ea in eas:
        last_seen_at = ea.last_seen_at
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=now.tzinfo)
        status = ea.status
        if now - last_seen_at > timeout_window:
            status = "offline"

        latest_command = db.scalar(
            select(Command)
            .where(Command.ea_id == ea.ea_id, Command.ea_id.in_(visible_ea_ids_stmt(principal)))
            .order_by(desc(Command.created_at))
            .limit(1)
        )

        risk_level = "normal"
        risk_text = "normal"
        if status == "offline":
            risk_level = "high"
            risk_text = "ea_offline"
        elif latest_command and latest_command.status in {CommandStatus.failed, CommandStatus.timeout}:
            risk_level = "high"
            risk_text = "recent_command_issue"
        elif latest_command and latest_command.status in {CommandStatus.pending, CommandStatus.received, CommandStatus.executing}:
            risk_level = "watch"
            risk_text = "command_in_progress"
        elif not ea.allow_trading:
            risk_level = "paused"
            risk_text = "trading_paused"

        result.append(
            {
                "ea_id": ea.ea_id,
                "account_number": ea.account_number,
                "broker": ea.broker,
                "terminal": ea.terminal,
                "strategy_name": ea.strategy_name,
                "version": ea.version,
                "status": status,
                "allow_trading": ea.allow_trading,
                "last_seen_at": ea.last_seen_at,
                "updated_at": ea.updated_at,
                "positions_count": position_counts.get(ea.ea_id, 0),
                "latest_snapshot_at": latest_snapshot_times.get(ea.ea_id),
                "latest_command_status": latest_command.status if latest_command else None,
                "latest_command_type": latest_command.command_type if latest_command else None,
                "latest_command_at": latest_command.updated_at if latest_command else None,
                "risk_level": risk_level,
                "risk_text": risk_text,
                "assigned_users": assigned_users_by_ea.get(ea.ea_id, []),
                "has_ea_token": bool(ea.api_token_hash),
            }
        )
    return result


@router.post("/eas", response_model=EAOut, status_code=status.HTTP_201_CREATED)
def create_or_update_ea(
    payload: EACreateIn,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> dict:
    require_admin_principal(principal)
    ea = db.scalar(select(EAInstance).where(EAInstance.ea_id == payload.ea_id))
    created = ea is None
    if ea is None:
        ea = EAInstance(ea_id=payload.ea_id)
        db.add(ea)

    ea.account_number = payload.account_number
    ea.broker = payload.broker
    ea.terminal = payload.terminal
    ea.strategy_name = payload.strategy_name
    ea.version = payload.version
    ea.status = payload.status
    ea.allow_trading = payload.allow_trading
    if payload.api_token:
        ea.api_token_hash = hash_password(payload.api_token)
        ea.api_token_enabled = True
    ea.last_seen_at = utc_now()
    write_audit_log(
        db,
        principal,
        action="ea.created" if created else "ea.updated",
        resource_type="ea",
        resource_id=payload.ea_id,
        details={
            "account_number": payload.account_number,
            "broker": payload.broker,
            "terminal": payload.terminal,
            "has_api_token": bool(payload.api_token),
        },
    )
    db.commit()
    db.refresh(ea)
    return {
        "ea_id": ea.ea_id,
        "account_number": ea.account_number,
        "broker": ea.broker,
        "terminal": ea.terminal,
        "strategy_name": ea.strategy_name,
        "version": ea.version,
        "status": ea.status,
        "allow_trading": ea.allow_trading,
        "last_seen_at": ea.last_seen_at,
        "updated_at": ea.updated_at,
        "assigned_users": [],
        "has_ea_token": bool(ea.api_token_hash),
        "risk_level": "normal",
        "risk_text": "created" if created else "updated",
    }


@router.post("/eas/{ea_id}/token", response_model=EATokenOut)
def rotate_ea_token(
    ea_id: str,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> EATokenOut:
    require_admin_principal(principal)
    ea = db.scalar(select(EAInstance).where(EAInstance.ea_id == ea_id))
    if ea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EA not found")
    token = "ea_" + secrets.token_urlsafe(32)
    ea.api_token_hash = hash_password(token)
    ea.api_token_enabled = True
    write_audit_log(
        db,
        principal,
        action="ea.token_rotated",
        resource_type="ea",
        resource_id=ea_id,
        details={"token_enabled": True},
    )
    db.commit()
    return EATokenOut(ea_id=ea_id, api_token=token, message="EA token generated; copy it now")


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[User]:
    require_admin_principal(principal)
    return list(db.scalars(select(User).order_by(User.username.asc())))


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[AuditLog]:
    require_admin_principal(principal)
    return list(db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)))


@router.get("/safety-config", response_model=SafetyConfigOut)
def safety_config(principal: AdminPrincipal = Depends(require_console_access)) -> SafetyConfigOut:
    require_admin_principal(principal)
    allowed_symbols = sorted(_allowed_trade_symbols())
    notes = [
        "即使请求绕过网页界面，后端仍会对影响交易的命令参数做校验。",
        "「暂停 / 恢复」只控制自动策略交易；手动平仓、撤单等命令仍应由 EA 照常处理。",
        "同一 EA 若存在另一条影响交易的命令处于待领取 / 已领取 / 执行中，会暂时锁定新的同类下发。",
    ]
    if allowed_symbols:
        notes.append("手动交易类命令仅接受白名单中配置的交易品种。")
    else:
        notes.append("当前未配置品种白名单：允许使用券商侧的任意品种符号（仍以其它服务端校验为准）。")
    return SafetyConfigOut(
        max_manual_order_volume=settings.max_manual_order_volume,
        allowed_trade_symbols=allowed_symbols,
        command_timeout_seconds=settings.command_timeout_seconds,
        ea_offline_seconds=settings.ea_offline_seconds,
        public_dashboard_preview_enabled=settings.allow_public_dashboard_preview,
        notes=notes,
    )


def _check_status(checks: list[SystemCheckItemOut]) -> str:
    if any(check.status == "error" for check in checks):
        return "error"
    if any(check.status == "warning" for check in checks):
        return "warning"
    return "ok"


def _token_check(key: str, title: str, value: str, weak_values: set[str]) -> SystemCheckItemOut:
    if not value:
        return SystemCheckItemOut(key=key, title=title, status="error", message="未配置，相关请求会被拒绝。")
    if value in weak_values:
        return SystemCheckItemOut(key=key, title=title, status="warning", message="仍在使用默认示例值，生产环境上线前必须替换。")
    if len(value) < 16:
        return SystemCheckItemOut(key=key, title=title, status="warning", message="长度偏短，建议使用更长的随机值。")
    return SystemCheckItemOut(key=key, title=title, status="ok", message="已配置，未在页面暴露具体值。")


@router.get("/system-checks", response_model=SystemCheckOut)
def system_checks(
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> SystemCheckOut:
    require_admin_principal(principal)
    checks: list[SystemCheckItemOut] = []

    try:
        db.execute(text("SELECT 1"))
        checks.append(SystemCheckItemOut(key="database", title="数据库连接", status="ok", message="数据库连接正常。"))
    except Exception as exc:
        checks.append(
            SystemCheckItemOut(
                key="database",
                title="数据库连接",
                status="error",
                message=f"数据库连接失败：{exc.__class__.__name__}",
            )
        )

    checks.extend(
        [
            _token_check(
                "admin_api_token",
                "后台 Token",
                settings.admin_api_token,
                {"change_this_admin_token", "admin123456", "test_admin_token"},
            ),
            _token_check(
                "ea_api_token",
                "EA API Token",
                settings.ea_api_token,
                {"change_this_ea_token", "ea123456", "test_ea_token"},
            ),
            _token_check(
                "jwt_secret",
                "JWT 密钥",
                settings.jwt_secret,
                {"change_this_jwt_secret", "test_jwt_secret"},
            ),
        ]
    )

    allowed_symbols = sorted(_allowed_trade_symbols())
    if allowed_symbols:
        checks.append(
            SystemCheckItemOut(
                key="allowed_trade_symbols",
                title="交易品种白名单",
                status="ok",
                message=f"已限制为：{', '.join(allowed_symbols)}。",
            )
        )
    else:
        checks.append(
            SystemCheckItemOut(
                key="allowed_trade_symbols",
                title="交易品种白名单",
                status="warning",
                message="未配置品种白名单，手动交易将允许任意券商符号。",
            )
        )

    if settings.max_manual_order_volume <= 0:
        checks.append(
            SystemCheckItemOut(key="max_manual_order_volume", title="最大手数", status="error", message="必须大于 0。")
        )
    else:
        checks.append(
            SystemCheckItemOut(
                key="max_manual_order_volume",
                title="最大手数",
                status="ok",
                message=f"当前手动开仓上限为 {settings.max_manual_order_volume} 手。",
            )
        )

    if settings.command_timeout_seconds <= 0:
        checks.append(SystemCheckItemOut(key="command_timeout", title="命令超时", status="error", message="必须大于 0 秒。"))
    else:
        checks.append(
            SystemCheckItemOut(
                key="command_timeout",
                title="命令超时",
                status="ok",
                message=f"未完成命令将在 {settings.command_timeout_seconds} 秒后超时。",
            )
        )

    if settings.ea_offline_seconds <= 0:
        checks.append(SystemCheckItemOut(key="ea_offline", title="EA 离线判定", status="error", message="必须大于 0 秒。"))
    else:
        checks.append(
            SystemCheckItemOut(
                key="ea_offline",
                title="EA 离线判定",
                status="ok",
                message=f"EA 超过 {settings.ea_offline_seconds} 秒未心跳会被标记为离线。",
            )
        )

    return SystemCheckOut(status=_check_status(checks), checks=checks)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateIn,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> User:
    require_admin_principal(principal)
    existing = db.scalar(select(User).where(User.username == payload.username))
    role = UserRole(payload.role)
    if existing:
        existing.password_hash = hash_password(payload.password)
        existing.role = role
        existing.is_active = True
        write_audit_log(
            db,
            principal,
            action="user.updated",
            resource_type="user",
            resource_id=payload.username,
            details={"role": payload.role, "reactivated": True},
        )
        db.commit()
        db.refresh(existing)
        return existing
    user = User(username=payload.username, password_hash=hash_password(payload.password), role=role)
    db.add(user)
    write_audit_log(
        db,
        principal,
        action="user.created",
        resource_type="user",
        resource_id=payload.username,
        details={"role": payload.role},
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{username}", response_model=UserOut)
def update_user(
    username: str,
    payload: UserUpdateIn,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> User:
    require_admin_principal(principal)
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.role is not None:
        user.role = UserRole(payload.role)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    write_audit_log(
        db,
        principal,
        action="user.updated",
        resource_type="user",
        resource_id=username,
        details=payload.model_dump(exclude_none=True),
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{username}", response_model=MessageOut)
def delete_user(
    username: str,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> dict[str, str]:
    require_admin_principal(principal)
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if principal.subject == username:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete the current user")

    assignment_count = db.scalar(select(func.count()).select_from(EAUserAssignment).where(EAUserAssignment.user_id == user.id))
    if assignment_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User has EA assignment history; revoke assignments and disable the user instead",
        )

    if user.role == UserRole.admin and user.is_active:
        active_admin_count = db.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.admin, User.is_active.is_(True))
        )
        if active_admin_count is not None and active_admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete the last active admin")

    write_audit_log(
        db,
        principal,
        action="user.deleted",
        resource_type="user",
        resource_id=username,
        details={"role": user.role.value, "was_active": user.is_active},
    )
    db.delete(user)
    db.commit()
    return {"message": f"User {username} deleted"}


@router.get("/assignments", response_model=list[EAAssignmentOut])
def list_assignments(
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[dict]:
    require_admin_principal(principal)
    rows = list(
        db.scalars(
            select(EAUserAssignment)
            .options(selectinload(EAUserAssignment.user))
            .where(EAUserAssignment.revoked_at.is_(None))
            .order_by(EAUserAssignment.ea_id.asc(), EAUserAssignment.created_at.desc())
        )
    )
    return [_assignment_out(row) for row in rows]


@router.get("/my-assignments", response_model=list[EAAssignmentOut])
def list_my_assignments(
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[dict]:
    if principal.role == UserRole.admin.value:
        rows = list(
            db.scalars(
                select(EAUserAssignment)
                .options(selectinload(EAUserAssignment.user))
                .where(EAUserAssignment.revoked_at.is_(None))
                .order_by(EAUserAssignment.ea_id.asc(), EAUserAssignment.created_at.desc())
            )
        )
        return [_assignment_out(row) for row in rows]

    rows = list(
        db.scalars(
            select(EAUserAssignment)
            .join(User, User.id == EAUserAssignment.user_id)
            .options(selectinload(EAUserAssignment.user))
            .where(
                User.username == principal.subject,
                User.is_active.is_(True),
                EAUserAssignment.revoked_at.is_(None),
                EAUserAssignment.can_view.is_(True),
            )
            .order_by(EAUserAssignment.ea_id.asc(), EAUserAssignment.created_at.desc())
        )
    )
    return [_assignment_out(row) for row in rows]


@router.post("/assignments", response_model=EAAssignmentOut, status_code=status.HTTP_201_CREATED)
def assign_ea_to_user(
    payload: EAAssignmentIn,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> dict:
    require_admin_principal(principal)
    ea = db.scalar(select(EAInstance).where(EAInstance.ea_id == payload.ea_id))
    if ea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EA not found")
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.is_primary_operator:
        current_primary = db.scalar(
            select(EAUserAssignment).where(
                EAUserAssignment.ea_id == payload.ea_id,
                EAUserAssignment.revoked_at.is_(None),
                EAUserAssignment.is_primary_operator.is_(True),
                EAUserAssignment.user_id != user.id,
            )
        )
        if current_primary is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="EA already has a primary operator")

    assignment = db.scalar(
        select(EAUserAssignment).where(EAUserAssignment.ea_id == payload.ea_id, EAUserAssignment.user_id == user.id)
    )
    if assignment is None:
        assignment = EAUserAssignment(ea_id=payload.ea_id, user_id=user.id, assigned_by=principal.subject)
        db.add(assignment)
    assignment.can_view = payload.can_view
    assignment.can_trade = payload.can_trade
    assignment.is_primary_operator = payload.is_primary_operator
    assignment.revoked_at = None
    write_audit_log(
        db,
        principal,
        action="assignment.upserted",
        resource_type="assignment",
        resource_id=f"{payload.ea_id}:{payload.username}",
        details={
            "ea_id": payload.ea_id,
            "username": payload.username,
            "can_view": payload.can_view,
            "can_trade": payload.can_trade,
            "is_primary_operator": payload.is_primary_operator,
        },
    )
    db.commit()
    db.refresh(assignment)
    assignment.user = user
    return _assignment_out(assignment)


@router.patch("/assignments/{assignment_id}", response_model=EAAssignmentOut)
def update_assignment(
    assignment_id: int,
    payload: EAAssignmentUpdateIn,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> dict:
    require_admin_principal(principal)
    assignment = db.scalar(
        select(EAUserAssignment)
        .options(selectinload(EAUserAssignment.user))
        .where(EAUserAssignment.id == assignment_id, EAUserAssignment.revoked_at.is_(None))
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    next_primary = assignment.is_primary_operator if payload.is_primary_operator is None else payload.is_primary_operator
    if next_primary:
        current_primary = db.scalar(
            select(EAUserAssignment).where(
                EAUserAssignment.ea_id == assignment.ea_id,
                EAUserAssignment.revoked_at.is_(None),
                EAUserAssignment.is_primary_operator.is_(True),
                EAUserAssignment.id != assignment.id,
            )
        )
        if current_primary is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="EA already has a primary operator")

    if payload.can_view is not None:
        assignment.can_view = payload.can_view
    if payload.can_trade is not None:
        assignment.can_trade = payload.can_trade
    if payload.is_primary_operator is not None:
        assignment.is_primary_operator = payload.is_primary_operator
    write_audit_log(
        db,
        principal,
        action="assignment.updated",
        resource_type="assignment",
        resource_id=str(assignment_id),
        details={
            "ea_id": assignment.ea_id,
            "username": assignment.user.username if assignment.user else None,
            **payload.model_dump(exclude_none=True),
        },
    )
    db.commit()
    db.refresh(assignment)
    return _assignment_out(assignment)


@router.delete("/assignments/{assignment_id}", response_model=EAAssignmentOut)
def revoke_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> dict:
    require_admin_principal(principal)
    assignment = db.scalar(
        select(EAUserAssignment).options(selectinload(EAUserAssignment.user)).where(EAUserAssignment.id == assignment_id)
    )
    if assignment is None or assignment.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    assignment.revoked_at = utc_now()
    write_audit_log(
        db,
        principal,
        action="assignment.revoked",
        resource_type="assignment",
        resource_id=str(assignment_id),
        details={"ea_id": assignment.ea_id, "username": assignment.user.username if assignment.user else None},
    )
    db.commit()
    db.refresh(assignment)
    return _assignment_out(assignment)


@router.get("/eas/{ea_id}/positions", response_model=list[PositionOut])
def list_positions(
    ea_id: str,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[Position]:
    require_ea_access(db, principal, ea_id)
    return list(db.scalars(select(Position).where(Position.ea_id == ea_id).order_by(Position.symbol.asc())))


@router.get("/eas/{ea_id}/snapshots", response_model=list[AccountSnapshotOut])
def list_snapshots(
    ea_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[AccountSnapshot]:
    require_ea_access(db, principal, ea_id)
    limit = max(1, min(limit, 500))
    return list(
        db.scalars(
            select(AccountSnapshot).where(AccountSnapshot.ea_id == ea_id).order_by(desc(AccountSnapshot.created_at)).limit(limit)
        )
    )


@router.post("/commands", response_model=CommandOut, status_code=status.HTTP_201_CREATED)
def create_command(
    payload: CommandCreateIn,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> Command:
    require_ea_access(db, principal, payload.ea_id, trade=True)
    validated_payload = validate_command_payload(payload)
    ensure_no_active_locked_command(db, payload.ea_id, payload.command_type)

    expires_at = payload.expires_at or (utc_now() + timedelta(seconds=settings.command_timeout_seconds))
    command = Command(
        ea_id=payload.ea_id,
        command_type=payload.command_type,
        status=CommandStatus.pending,
        payload=validated_payload,
        requested_by=payload.requested_by or principal.subject,
        expires_at=expires_at,
    )
    command.logs.append(CommandLog(status=CommandStatus.pending, message="Command created by admin"))
    db.add(command)
    write_audit_log(
        db,
        principal,
        action="command.created",
        resource_type="command",
        resource_id=payload.ea_id,
        details={
            "ea_id": payload.ea_id,
            "command_type": getattr(payload.command_type, "value", str(payload.command_type)),
            "requested_by": payload.requested_by or principal.subject,
            "payload_summary": command_payload_summary(validated_payload),
        },
    )
    db.commit()
    db.refresh(command)
    return command


@router.get("/commands", response_model=list[CommandOut])
def list_commands(
    ea_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> list[Command]:
    mark_timed_out_commands(db)
    db.commit()

    stmt = (
        select(Command)
        .options(selectinload(Command.logs))
        .where(Command.ea_id.in_(visible_ea_ids_stmt(principal)))
        .order_by(desc(Command.created_at))
        .limit(limit)
    )
    if ea_id:
        require_ea_access(db, principal, ea_id)
        stmt = (
            select(Command)
            .options(selectinload(Command.logs))
            .where(Command.ea_id == ea_id, Command.ea_id.in_(visible_ea_ids_stmt(principal)))
            .order_by(desc(Command.created_at))
            .limit(limit)
        )
    return list(db.scalars(stmt))


@router.post("/commands/{command_id}/cancel", response_model=CommandOut)
def cancel_command(
    command_id: int,
    db: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_console_access),
) -> Command:
    command = db.get(Command, command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")
    require_ea_access(db, principal, command.ea_id, trade=True)
    if command.status not in {CommandStatus.pending, CommandStatus.received}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending or received commands can be cancelled")

    command.status = CommandStatus.cancelled
    command.logs.append(CommandLog(status=CommandStatus.cancelled, message="Command cancelled by admin"))
    write_audit_log(
        db,
        principal,
        action="command.cancelled",
        resource_type="command",
        resource_id=str(command_id),
        details={"ea_id": command.ea_id, "command_type": command.command_type.value},
    )
    db.commit()
    db.refresh(command)
    return command