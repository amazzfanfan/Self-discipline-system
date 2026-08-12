"""add structured goal metrics

Revision ID: e2489f63a0cb
Revises: d13c8f2a714e
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e2489f63a0cb"
down_revision: str | Sequence[str] | None = "d13c8f2a714e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("goals", sa.Column("target_unit", sa.String(length=30), nullable=True))
    op.add_column(
        "goals",
        sa.Column("metric_direction", sa.String(length=12), nullable=False, server_default="increase"),
    )
    op.add_column("goals", sa.Column("baseline_value", sa.Float(), nullable=True))
    op.execute("UPDATE goals SET baseline_value = current_value WHERE baseline_value IS NULL")


def downgrade() -> None:
    op.drop_column("goals", "baseline_value")
    op.drop_column("goals", "metric_direction")
    op.drop_column("goals", "target_unit")
