"""add ea lifecycle fields

Revision ID: 20260512_0004
Revises: 20260512_0003
Create Date: 2026-05-12 22:05:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260512_0004"
down_revision: str | None = "20260512_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ea_lifecycle_status = sa.Enum("active", "paused", "archived", "disabled", name="ea_lifecycle_status")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        ea_lifecycle_status.create(bind, checkfirst=True)
        lifecycle_type = ea_lifecycle_status
    else:
        lifecycle_type = sa.String(length=32)

    op.add_column("ea_instances", sa.Column("lifecycle_status", lifecycle_type, nullable=False, server_default="active"))
    op.add_column("ea_instances", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ea_instances", sa.Column("archived_by", sa.String(length=128), nullable=True))
    op.add_column("ea_instances", sa.Column("archive_reason", sa.Text(), nullable=True))
    op.create_index(op.f("ix_ea_instances_archived_at"), "ea_instances", ["archived_at"], unique=False)
    op.alter_column("ea_instances", "lifecycle_status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_ea_instances_archived_at"), table_name="ea_instances")
    op.drop_column("ea_instances", "archive_reason")
    op.drop_column("ea_instances", "archived_by")
    op.drop_column("ea_instances", "archived_at")
    op.drop_column("ea_instances", "lifecycle_status")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        ea_lifecycle_status.drop(bind, checkfirst=True)
