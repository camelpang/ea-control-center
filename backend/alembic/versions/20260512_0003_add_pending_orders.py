"""add pending orders

Revision ID: 20260512_0003
Revises: 20260512_0002
Create Date: 2026-05-12 18:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260512_0003"
down_revision: str | None = "20260512_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ea_id", sa.String(length=128), sa.ForeignKey("ea_instances.ea_id"), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("account_snapshots.id"), nullable=True),
        sa.Column("ticket", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=True),
        sa.Column("volume", sa.Numeric(18, 6), nullable=True),
        sa.Column("price", sa.Numeric(18, 6), nullable=True),
        sa.Column("sl", sa.Numeric(18, 6), nullable=True),
        sa.Column("tp", sa.Numeric(18, 6), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.UniqueConstraint("ea_id", "ticket", name="uq_pending_orders_ea_ticket"),
    )
    op.create_index(op.f("ix_pending_orders_ea_id"), "pending_orders", ["ea_id"], unique=False)
    op.create_index(op.f("ix_pending_orders_snapshot_id"), "pending_orders", ["snapshot_id"], unique=False)
    op.create_index(op.f("ix_pending_orders_symbol"), "pending_orders", ["symbol"], unique=False)
    op.create_index(op.f("ix_pending_orders_ticket"), "pending_orders", ["ticket"], unique=False)
    op.create_index("ix_pending_orders_ea_symbol", "pending_orders", ["ea_id", "symbol"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pending_orders_ea_symbol", table_name="pending_orders")
    op.drop_index(op.f("ix_pending_orders_ticket"), table_name="pending_orders")
    op.drop_index(op.f("ix_pending_orders_symbol"), table_name="pending_orders")
    op.drop_index(op.f("ix_pending_orders_snapshot_id"), table_name="pending_orders")
    op.drop_index(op.f("ix_pending_orders_ea_id"), table_name="pending_orders")
    op.drop_table("pending_orders")
