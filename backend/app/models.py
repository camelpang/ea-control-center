import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CommandStatus(str, enum.Enum):
    pending = "pending"
    received = "received"
    executing = "executing"
    success = "success"
    failed = "failed"
    timeout = "timeout"
    cancelled = "cancelled"


class CommandType(str, enum.Enum):
    pause_trading = "pause_trading"
    resume_trading = "resume_trading"
    close_all = "close_all"
    close_symbol = "close_symbol"
    close_ticket = "close_ticket"
    cancel_order = "cancel_order"
    manual_manage = "manual_manage"
    manual_release = "manual_release"
    open_order = "open_order"
    update_params = "update_params"


class UserRole(str, enum.Enum):
    admin = "admin"
    viewer = "viewer"


class EALifecycleStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"
    disabled = "disabled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.admin)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EAInstance(Base):
    __tablename__ = "ea_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ea_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    account_number: Mapped[str | None] = mapped_column(String(64), index=True)
    broker: Mapped[str | None] = mapped_column(String(128))
    terminal: Mapped[str | None] = mapped_column(String(32))
    strategy_name: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="online")
    lifecycle_status: Mapped[EALifecycleStatus] = mapped_column(
        Enum(EALifecycleStatus, name="ea_lifecycle_status"), default=EALifecycleStatus.active
    )
    allow_trading: Mapped[bool] = mapped_column(Boolean, default=True)
    api_token_hash: Mapped[str | None] = mapped_column(String(255))
    api_token_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    archived_by: Mapped[str | None] = mapped_column(String(128))
    archive_reason: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    snapshots: Mapped[list["AccountSnapshot"]] = relationship(back_populates="ea")
    commands: Mapped[list["Command"]] = relationship(back_populates="ea")
    assignments: Mapped[list["EAUserAssignment"]] = relationship(back_populates="ea", cascade="all, delete-orphan")


class EAUserAssignment(Base):
    __tablename__ = "ea_user_assignments"
    __table_args__ = (
        UniqueConstraint("ea_id", "user_id", name="uq_ea_user_assignment"),
        Index("ix_ea_user_assignments_user_active", "user_id", "revoked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ea_id: Mapped[str] = mapped_column(String(128), ForeignKey("ea_instances.ea_id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    can_view: Mapped[bool] = mapped_column(Boolean, default=True)
    can_trade: Mapped[bool] = mapped_column(Boolean, default=False)
    is_primary_operator: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    ea: Mapped[EAInstance] = relationship(back_populates="assignments")
    user: Mapped[User] = relationship()


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ea_id: Mapped[str] = mapped_column(String(128), ForeignKey("ea_instances.ea_id"), index=True)
    account_number: Mapped[str | None] = mapped_column(String(64), index=True)
    currency: Mapped[str | None] = mapped_column(String(16))
    balance: Mapped[float | None] = mapped_column(Numeric(18, 6))
    equity: Mapped[float | None] = mapped_column(Numeric(18, 6))
    margin: Mapped[float | None] = mapped_column(Numeric(18, 6))
    free_margin: Mapped[float | None] = mapped_column(Numeric(18, 6))
    margin_level: Mapped[float | None] = mapped_column(Numeric(18, 6))
    profit: Mapped[float | None] = mapped_column(Numeric(18, 6))
    raw: Mapped[dict | None] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    ea: Mapped[EAInstance] = relationship(back_populates="snapshots")
    positions: Mapped[list["Position"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("ea_id", "ticket", name="uq_positions_ea_ticket"),
        Index("ix_positions_ea_symbol", "ea_id", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ea_id: Mapped[str] = mapped_column(String(128), ForeignKey("ea_instances.ea_id"), index=True)
    snapshot_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("account_snapshots.id"))
    ticket: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(16))
    volume: Mapped[float | None] = mapped_column(Numeric(18, 6))
    open_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    current_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    sl: Mapped[float | None] = mapped_column(Numeric(18, 6))
    tp: Mapped[float | None] = mapped_column(Numeric(18, 6))
    profit: Mapped[float | None] = mapped_column(Numeric(18, 6))
    swap: Mapped[float | None] = mapped_column(Numeric(18, 6))
    commission: Mapped[float | None] = mapped_column(Numeric(18, 6))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    raw: Mapped[dict | None] = mapped_column(JSON_TYPE)

    snapshot: Mapped[AccountSnapshot | None] = relationship(back_populates="positions")


class PendingOrder(Base):
    __tablename__ = "pending_orders"
    __table_args__ = (
        UniqueConstraint("ea_id", "ticket", name="uq_pending_orders_ea_ticket"),
        Index("ix_pending_orders_ea_symbol", "ea_id", "symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ea_id: Mapped[str] = mapped_column(String(128), ForeignKey("ea_instances.ea_id"), index=True)
    snapshot_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("account_snapshots.id"))
    ticket: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    order_type: Mapped[str] = mapped_column(String(32))
    side: Mapped[str | None] = mapped_column(String(16))
    volume: Mapped[float | None] = mapped_column(Numeric(18, 6))
    price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    sl: Mapped[float | None] = mapped_column(Numeric(18, 6))
    tp: Mapped[float | None] = mapped_column(Numeric(18, 6))
    state: Mapped[str | None] = mapped_column(String(32))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    raw: Mapped[dict | None] = mapped_column(JSON_TYPE)


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (Index("ix_commands_ea_status", "ea_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ea_id: Mapped[str] = mapped_column(String(128), ForeignKey("ea_instances.ea_id"), index=True)
    command_type: Mapped[CommandType] = mapped_column(Enum(CommandType, name="command_type"))
    status: Mapped[CommandStatus] = mapped_column(Enum(CommandStatus, name="command_status"), default=CommandStatus.pending)
    payload: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    requested_by: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    ea: Mapped[EAInstance] = relationship(back_populates="commands")
    logs: Mapped[list["CommandLog"]] = relationship(back_populates="command", cascade="all, delete-orphan")


class CommandLog(Base):
    __tablename__ = "command_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    command_id: Mapped[int] = mapped_column(Integer, ForeignKey("commands.id"), index=True)
    status: Mapped[CommandStatus] = mapped_column(Enum(CommandStatus, name="command_status"))
    message: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict | None] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    command: Mapped[Command] = relationship(back_populates="logs")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_resource", "resource_type", "resource_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(128), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), index=True)
    details: Mapped[dict | None] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
