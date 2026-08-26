"""unify daily weight records

Revision ID: f7b1c2d3e4a5
Revises: e2489f63a0cb
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f7b1c2d3e4a5"
down_revision: str | Sequence[str] | None = "e2489f63a0cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weight_records",
        sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
    )
    # Preserve the most recently created measurement for each business day
    # before enforcing the one-measurement-per-day invariant.
    op.execute(
        """
        DELETE FROM weight_records older
        USING weight_records newer
        WHERE older.user_id = newer.user_id
          AND older.recorded_at = newer.recorded_at
          AND (
            older.created_at < newer.created_at
            OR (older.created_at = newer.created_at AND older.id::text < newer.id::text)
          )
        """
    )
    op.create_unique_constraint(
        "uq_weight_records_user_date",
        "weight_records",
        ["user_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_weight_records_user_date",
        "weight_records",
        type_="unique",
    )
    op.drop_column("weight_records", "source")
