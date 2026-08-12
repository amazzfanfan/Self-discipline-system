"""add task feasibility constraints

Revision ID: b1824f09d1ef
Revises: fd821ac4b9d2
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b1824f09d1ef"
down_revision: str | Sequence[str] | None = "fd821ac4b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("task_constraints", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "task_constraints")
