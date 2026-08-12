"""add notification quiet hours

Revision ID: fd821ac4b9d2
Revises: f9036bd72a10
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "fd821ac4b9d2"
down_revision: str | Sequence[str] | None = "f9036bd72a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("notification_quiet_start", sa.Time()))
    op.add_column("user_profiles", sa.Column("notification_quiet_end", sa.Time()))


def downgrade() -> None:
    op.drop_column("user_profiles", "notification_quiet_end")
    op.drop_column("user_profiles", "notification_quiet_start")
