"""sync command_type enum

Revision ID: 20260512_0002
Revises: 20260511_0001
Create Date: 2026-05-12 17:35:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260512_0002"
down_revision: str | None = "20260511_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for value in ("cancel_order", "manual_manage", "manual_release"):
        op.execute(f"ALTER TYPE command_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot safely remove enum values in-place without rebuilding
    # dependent columns. Leaving the values is the least risky rollback path.
    pass
