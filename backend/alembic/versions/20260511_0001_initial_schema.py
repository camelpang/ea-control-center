"""initial schema

Revision ID: 20260511_0001
Revises:
Create Date: 2026-05-11 09:45:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260511_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


command_status = sa.Enum(
    "pending",
    "received",
    "executing",
    "success",
    "failed",
    "timeout",
    "cancelled",
    name="command_status",
)
command_type = sa.Enum(
    "pause_trading",
    "resume_trading",
    "close_all",
    "close_symbol",
    "close_ticket",
    "cancel_order",
    "manual_manage",
    "manual_release",
    "open_order",
    "update_params",
    name="command_type",
)
user_role = sa.Enum("admin", "viewer", name="user_role")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "ea_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ea_id", sa.String(length=128), nullable=False),
        sa.Column("account_number", sa.String(length=64), nullable=True),
        sa.Column("broker", sa.String(length=128), nullable=True),
        sa.Column("terminal", sa.String(length=32), nullable=True),
        sa.Column("strategy_name", sa.String(length=128), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("allow_trading", sa.Boolean(), nullable=False),
        sa.Column("api_token_hash", sa.String(length=255), nullable=True),
        sa.Column("api_token_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_ea_instances_account_number"), "ea_instances", ["account_number"], unique=False)
    op.create_index(op.f("ix_ea_instances_ea_id"), "ea_instances", ["ea_id"], unique=True)

    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ea_id", sa.String(length=128), sa.ForeignKey("ea_instances.ea_id"), nullable=False),
        sa.Column("account_number", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("balance", sa.Numeric(18, 6), nullable=True),
        sa.Column("equity", sa.Numeric(18, 6), nullable=True),
        sa.Column("margin", sa.Numeric(18, 6), nullable=True),
        sa.Column("free_margin", sa.Numeric(18, 6), nullable=True),
        sa.Column("margin_level", sa.Numeric(18, 6), nullable=True),
        sa.Column("profit", sa.Numeric(18, 6), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_account_snapshots_account_number"), "account_snapshots", ["account_number"], unique=False)
    op.create_index(op.f("ix_account_snapshots_created_at"), "account_snapshots", ["created_at"], unique=False)
    op.create_index(op.f("ix_account_snapshots_ea_id"), "account_snapshots", ["ea_id"], unique=False)

    op.create_table(
        "commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ea_id", sa.String(length=128), sa.ForeignKey("ea_instances.ea_id"), nullable=False),
        sa.Column("command_type", command_type, nullable=False),
        sa.Column("status", command_status, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_commands_created_at"), "commands", ["created_at"], unique=False)
    op.create_index(op.f("ix_commands_ea_id"), "commands", ["ea_id"], unique=False)
    op.create_index("ix_commands_ea_status", "commands", ["ea_id", "status"], unique=False)

    op.create_table(
        "ea_user_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ea_id", sa.String(length=128), sa.ForeignKey("ea_instances.ea_id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("can_view", sa.Boolean(), nullable=False),
        sa.Column("can_trade", sa.Boolean(), nullable=False),
        sa.Column("is_primary_operator", sa.Boolean(), nullable=False),
        sa.Column("assigned_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ea_id", "user_id", name="uq_ea_user_assignment"),
    )
    op.create_index(op.f("ix_ea_user_assignments_ea_id"), "ea_user_assignments", ["ea_id"], unique=False)
    op.create_index(op.f("ix_ea_user_assignments_revoked_at"), "ea_user_assignments", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_ea_user_assignments_user_id"), "ea_user_assignments", ["user_id"], unique=False)
    op.create_index("ix_ea_user_assignments_user_active", "ea_user_assignments", ["user_id", "revoked_at"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_actor"), "audit_logs", ["actor"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_logs_resource_id"), "audit_logs", ["resource_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_resource_type"), "audit_logs", ["resource_type"], unique=False)
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"], unique=False)

    op.create_table(
        "command_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("command_id", sa.Integer(), sa.ForeignKey("commands.id"), nullable=False),
        sa.Column("status", command_status, nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_command_logs_command_id"), "command_logs", ["command_id"], unique=False)
    op.create_index(op.f("ix_command_logs_created_at"), "command_logs", ["created_at"], unique=False)

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ea_id", sa.String(length=128), sa.ForeignKey("ea_instances.ea_id"), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("account_snapshots.id"), nullable=True),
        sa.Column("ticket", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("volume", sa.Numeric(18, 6), nullable=True),
        sa.Column("open_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("current_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("sl", sa.Numeric(18, 6), nullable=True),
        sa.Column("tp", sa.Numeric(18, 6), nullable=True),
        sa.Column("profit", sa.Numeric(18, 6), nullable=True),
        sa.Column("swap", sa.Numeric(18, 6), nullable=True),
        sa.Column("commission", sa.Numeric(18, 6), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.UniqueConstraint("ea_id", "ticket", name="uq_positions_ea_ticket"),
    )
    op.create_index(op.f("ix_positions_ea_id"), "positions", ["ea_id"], unique=False)
    op.create_index(op.f("ix_positions_symbol"), "positions", ["symbol"], unique=False)
    op.create_index(op.f("ix_positions_ticket"), "positions", ["ticket"], unique=False)
    op.create_index("ix_positions_ea_symbol", "positions", ["ea_id", "symbol"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_positions_ea_symbol", table_name="positions")
    op.drop_index(op.f("ix_positions_ticket"), table_name="positions")
    op.drop_index(op.f("ix_positions_symbol"), table_name="positions")
    op.drop_index(op.f("ix_positions_ea_id"), table_name="positions")
    op.drop_table("positions")

    op.drop_index(op.f("ix_command_logs_created_at"), table_name="command_logs")
    op.drop_index(op.f("ix_command_logs_command_id"), table_name="command_logs")
    op.drop_table("command_logs")

    op.drop_index("ix_audit_logs_resource", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_resource_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_resource_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_ea_user_assignments_user_active", table_name="ea_user_assignments")
    op.drop_index(op.f("ix_ea_user_assignments_user_id"), table_name="ea_user_assignments")
    op.drop_index(op.f("ix_ea_user_assignments_revoked_at"), table_name="ea_user_assignments")
    op.drop_index(op.f("ix_ea_user_assignments_ea_id"), table_name="ea_user_assignments")
    op.drop_table("ea_user_assignments")

    op.drop_index("ix_commands_ea_status", table_name="commands")
    op.drop_index(op.f("ix_commands_ea_id"), table_name="commands")
    op.drop_index(op.f("ix_commands_created_at"), table_name="commands")
    op.drop_table("commands")

    op.drop_index(op.f("ix_account_snapshots_ea_id"), table_name="account_snapshots")
    op.drop_index(op.f("ix_account_snapshots_created_at"), table_name="account_snapshots")
    op.drop_index(op.f("ix_account_snapshots_account_number"), table_name="account_snapshots")
    op.drop_table("account_snapshots")

    op.drop_index(op.f("ix_ea_instances_ea_id"), table_name="ea_instances")
    op.drop_index(op.f("ix_ea_instances_account_number"), table_name="ea_instances")
    op.drop_table("ea_instances")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        user_role.drop(bind, checkfirst=True)
        command_type.drop(bind, checkfirst=True)
        command_status.drop(bind, checkfirst=True)
