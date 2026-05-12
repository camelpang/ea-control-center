from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import CommandStatus, CommandType

EA_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"
EA_ID_HELP = "EA ID must be 3-128 chars and use only letters, numbers, dot, underscore, hyphen, or colon"


class HeartbeatIn(BaseModel):
    ea_id: str = Field(min_length=3, max_length=128, pattern=EA_ID_PATTERN, description=EA_ID_HELP)
    account_number: str | None = None
    broker: str | None = None
    terminal: Literal["MT4", "MT5"] | str | None = None
    strategy_name: str | None = None
    version: str | None = None
    status: str = "online"
    allow_trading: bool | None = None


class PositionIn(BaseModel):
    ticket: str
    symbol: str
    side: Literal["buy", "sell"] | str
    volume: Decimal | None = None
    open_price: Decimal | None = None
    current_price: Decimal | None = None
    sl: Decimal | None = None
    tp: Decimal | None = None
    profit: Decimal | None = None
    swap: Decimal | None = None
    commission: Decimal | None = None
    opened_at: datetime | None = None
    raw: dict[str, Any] | None = None


class PendingOrderIn(BaseModel):
    ticket: str
    symbol: str
    order_type: str
    side: Literal["buy", "sell"] | str | None = None
    volume: Decimal | None = None
    price: Decimal | None = None
    sl: Decimal | None = None
    tp: Decimal | None = None
    state: str | None = None
    opened_at: datetime | None = None
    raw: dict[str, Any] | None = None


class SnapshotIn(BaseModel):
    ea_id: str = Field(min_length=3, max_length=128, pattern=EA_ID_PATTERN, description=EA_ID_HELP)
    account_number: str | None = None
    currency: str | None = None
    balance: Decimal | None = None
    equity: Decimal | None = None
    margin: Decimal | None = None
    free_margin: Decimal | None = None
    margin_level: Decimal | None = None
    profit: Decimal | None = None
    positions: list[PositionIn] = Field(default_factory=list)
    pending_orders: list[PendingOrderIn] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class CommandCreateIn(BaseModel):
    ea_id: str = Field(min_length=3, max_length=128, pattern=EA_ID_PATTERN, description=EA_ID_HELP)
    command_type: CommandType
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str | None = "admin"
    expires_at: datetime | None = None


class EACreateIn(BaseModel):
    ea_id: str = Field(min_length=3, max_length=128, pattern=EA_ID_PATTERN, description=EA_ID_HELP)
    account_number: str | None = None
    broker: str | None = None
    terminal: Literal["MT4", "MT5"] | str | None = None
    strategy_name: str | None = None
    version: str | None = None
    status: str = "manual"
    allow_trading: bool = True
    api_token: str | None = Field(default=None, min_length=8, max_length=256)


class CommandResultIn(BaseModel):
    status: CommandStatus
    message: str | None = None
    raw: dict[str, Any] | None = None


class EAOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ea_id: str
    account_number: str | None
    broker: str | None
    terminal: str | None
    strategy_name: str | None
    version: str | None
    status: str
    allow_trading: bool
    last_seen_at: datetime
    updated_at: datetime
    positions_count: int = 0
    pending_orders_count: int = 0
    latest_snapshot_at: datetime | None = None
    latest_command_status: CommandStatus | None = None
    latest_command_type: CommandType | None = None
    latest_command_at: datetime | None = None
    risk_level: str = "normal"
    risk_text: str | None = None
    assigned_users: list[str] = Field(default_factory=list)
    has_ea_token: bool = False


class EATokenOut(BaseModel):
    ea_id: str
    api_token: str
    message: str


class EADashboardCardOut(EAOut):
    """EA 一览 + 最新账户快照中的资金字段（用于监控大屏）。"""

    currency: str | None = None
    balance: Decimal | None = None
    equity: Decimal | None = None
    margin: Decimal | None = None
    free_margin: Decimal | None = None
    margin_level: Decimal | None = None
    snapshot_profit: Decimal | None = None


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket: str
    symbol: str
    side: str
    volume: Decimal | None
    open_price: Decimal | None
    current_price: Decimal | None
    sl: Decimal | None
    tp: Decimal | None
    profit: Decimal | None
    updated_at: datetime


class PendingOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket: str
    symbol: str
    order_type: str
    side: str | None
    volume: Decimal | None
    price: Decimal | None
    sl: Decimal | None
    tp: Decimal | None
    state: str | None
    updated_at: datetime


class AccountSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ea_id: str
    account_number: str | None
    currency: str | None
    balance: Decimal | None
    equity: Decimal | None
    margin: Decimal | None
    free_margin: Decimal | None
    margin_level: Decimal | None
    profit: Decimal | None
    created_at: datetime


class CommandLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: CommandStatus
    message: str | None
    raw: dict[str, Any] | None
    created_at: datetime


class CommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ea_id: str
    command_type: CommandType
    status: CommandStatus
    payload: dict[str, Any]
    requested_by: str | None
    error_message: str | None
    expires_at: datetime | None
    received_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    logs: list[CommandLogOut] = Field(default_factory=list)


class SnapshotAck(BaseModel):
    ea_id: str
    snapshot_id: int
    positions_count: int
    pending_orders_count: int = 0


class MessageOut(BaseModel):
    message: str


class UserCreateIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    role: Literal["admin", "viewer"] = "viewer"


class UserUpdateIn(BaseModel):
    role: Literal["admin", "viewer"] | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime


class EAAssignmentIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    ea_id: str = Field(min_length=3, max_length=128, pattern=EA_ID_PATTERN, description=EA_ID_HELP)
    can_view: bool = True
    can_trade: bool = False
    is_primary_operator: bool = False


class EAAssignmentUpdateIn(BaseModel):
    can_view: bool | None = None
    can_trade: bool | None = None
    is_primary_operator: bool | None = None


class EAAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ea_id: str
    username: str
    can_view: bool
    can_trade: bool
    is_primary_operator: bool
    assigned_by: str | None
    created_at: datetime
    revoked_at: datetime | None = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: str
    actor_role: str | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict[str, Any] | None = None
    created_at: datetime


class SafetyConfigOut(BaseModel):
    max_manual_order_volume: float
    allowed_trade_symbols: list[str]
    command_timeout_seconds: int
    ea_offline_seconds: int
    public_dashboard_preview_enabled: bool
    notes: list[str] = Field(default_factory=list)


class SystemCheckItemOut(BaseModel):
    key: str
    title: str
    status: Literal["ok", "warning", "error"]
    message: str


class SystemCheckOut(BaseModel):
    status: Literal["ok", "warning", "error"]
    checks: list[SystemCheckItemOut]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserPublicOut(BaseModel):
    username: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublicOut