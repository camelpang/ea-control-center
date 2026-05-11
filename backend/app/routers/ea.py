from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AccountSnapshot, AuditLog, Command, CommandLog, CommandStatus, CommandType, EAInstance, Position, utc_now
from app.schemas import CommandOut, CommandResultIn, HeartbeatIn, MessageOut, SnapshotAck, SnapshotIn
from app.security import verify_password

router = APIRouter()


def mark_timed_out_commands(db: Session) -> None:
    now = utc_now()
    timed_out = list(
        db.scalars(
            select(Command).where(
                and_(
                    Command.status.in_([CommandStatus.pending, CommandStatus.received]),
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


def write_ea_audit_log(db: Session, *, ea_id: str, action: str, resource_id: str, details: dict) -> None:
    db.add(
        AuditLog(
            actor=f"ea:{ea_id}",
            actor_role="ea",
            action=action,
            resource_type="command",
            resource_id=resource_id,
            details=details,
        )
    )


def get_or_create_ea(db: Session, ea_id: str) -> EAInstance:
    ea = db.scalar(select(EAInstance).where(EAInstance.ea_id == ea_id))
    if ea:
        return ea
    ea = EAInstance(ea_id=ea_id)
    db.add(ea)
    db.flush()
    return ea


def verify_ea_access(db: Session, ea_id: str, x_ea_token: str | None) -> None:
    if x_ea_token == settings.ea_api_token:
        return

    ea = db.scalar(select(EAInstance).where(EAInstance.ea_id == ea_id))
    if ea and ea.api_token_enabled and ea.api_token_hash and x_ea_token:
        if verify_password(x_ea_token, ea.api_token_hash):
            return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid EA token")


@router.post("/heartbeat", response_model=MessageOut)
def heartbeat(
    payload: HeartbeatIn,
    db: Session = Depends(get_db),
    x_ea_token: str | None = Header(default=None, alias="X-EA-Token"),
) -> MessageOut:
    verify_ea_access(db, payload.ea_id, x_ea_token)
    ea = get_or_create_ea(db, payload.ea_id)
    ea.account_number = payload.account_number or ea.account_number
    ea.broker = payload.broker or ea.broker
    ea.terminal = payload.terminal or ea.terminal
    ea.strategy_name = payload.strategy_name or ea.strategy_name
    ea.version = payload.version or ea.version
    ea.status = payload.status
    if payload.allow_trading is not None:
        ea.allow_trading = payload.allow_trading
    ea.last_seen_at = utc_now()
    db.commit()
    return MessageOut(message="heartbeat accepted")


@router.post("/snapshot", response_model=SnapshotAck)
def snapshot(
    payload: SnapshotIn,
    db: Session = Depends(get_db),
    x_ea_token: str | None = Header(default=None, alias="X-EA-Token"),
) -> SnapshotAck:
    verify_ea_access(db, payload.ea_id, x_ea_token)
    ea = get_or_create_ea(db, payload.ea_id)
    ea.account_number = payload.account_number or ea.account_number
    ea.last_seen_at = utc_now()
    ea.status = "online"

    account_snapshot = AccountSnapshot(
        ea_id=payload.ea_id,
        account_number=payload.account_number,
        currency=payload.currency,
        balance=payload.balance,
        equity=payload.equity,
        margin=payload.margin,
        free_margin=payload.free_margin,
        margin_level=payload.margin_level,
        profit=payload.profit,
        raw=payload.raw,
    )
    db.add(account_snapshot)
    db.flush()

    # The positions table represents the latest known open positions for this EA.
    db.query(Position).filter(Position.ea_id == payload.ea_id).delete(synchronize_session=False)
    for item in payload.positions:
        db.add(
            Position(
                ea_id=payload.ea_id,
                snapshot_id=account_snapshot.id,
                ticket=item.ticket,
                symbol=item.symbol,
                side=item.side,
                volume=item.volume,
                open_price=item.open_price,
                current_price=item.current_price,
                sl=item.sl,
                tp=item.tp,
                profit=item.profit,
                swap=item.swap,
                commission=item.commission,
                opened_at=item.opened_at,
                raw=item.raw,
            )
        )

    db.commit()
    return SnapshotAck(ea_id=payload.ea_id, snapshot_id=account_snapshot.id, positions_count=len(payload.positions))


@router.get("/commands", response_model=list[CommandOut])
def list_commands(
    ea_id: str,
    db: Session = Depends(get_db),
    x_ea_token: str | None = Header(default=None, alias="X-EA-Token"),
) -> list[Command]:
    verify_ea_access(db, ea_id, x_ea_token)
    mark_timed_out_commands(db)

    now = datetime.now(timezone.utc)
    commands = list(
        db.scalars(
            select(Command)
            .where(
                and_(
                    Command.ea_id == ea_id,
                    Command.status == CommandStatus.pending,
                    or_(Command.expires_at.is_(None), Command.expires_at > now),
                )
            )
            .order_by(Command.created_at.asc())
            .limit(20)
        )
    )

    for command in commands:
        command.status = CommandStatus.received
        command.received_at = utc_now()
        command.logs.append(CommandLog(status=CommandStatus.received, message="Command fetched by EA"))

    db.commit()
    return commands


@router.post("/commands/{command_id}/result", response_model=CommandOut)
def command_result(
    command_id: int,
    payload: CommandResultIn,
    db: Session = Depends(get_db),
    x_ea_token: str | None = Header(default=None, alias="X-EA-Token"),
) -> Command:
    command = db.get(Command, command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")
    verify_ea_access(db, command.ea_id, x_ea_token)

    command.status = payload.status
    if payload.status in {CommandStatus.success, CommandStatus.failed, CommandStatus.timeout, CommandStatus.cancelled}:
        command.completed_at = utc_now()
    if payload.status == CommandStatus.failed:
        command.error_message = payload.message

    if payload.status == CommandStatus.success:
        ea = db.scalar(select(EAInstance).where(EAInstance.ea_id == command.ea_id))
        if ea and command.command_type == CommandType.pause_trading:
            ea.allow_trading = False
        if ea and command.command_type == CommandType.resume_trading:
            ea.allow_trading = True

    command.logs.append(CommandLog(status=payload.status, message=payload.message, raw=payload.raw))
    write_ea_audit_log(
        db,
        ea_id=command.ea_id,
        action="command.result",
        resource_id=str(command.id),
        details={
            "ea_id": command.ea_id,
            "command_id": command.id,
            "command_type": command.command_type.value,
            "status": payload.status.value,
            "message": payload.message,
        },
    )
    db.commit()
    db.refresh(command)
    return command