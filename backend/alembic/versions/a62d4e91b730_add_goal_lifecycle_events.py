"""add goal lifecycle events

Revision ID: a62d4e91b730
Revises: e83f7a6c419d
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a62d4e91b730"
down_revision: Union[str, Sequence[str], None] = "e83f7a6c419d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "goal_lifecycle_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("previous_state", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("new_state", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("actor", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_goal_lifecycle_goal_created",
        "goal_lifecycle_events",
        ["goal_id", "created_at"],
    )
    op.create_index(
        "ix_goal_lifecycle_user_created",
        "goal_lifecycle_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_goal_lifecycle_user_created", table_name="goal_lifecycle_events")
    op.drop_index("ix_goal_lifecycle_goal_created", table_name="goal_lifecycle_events")
    op.drop_table("goal_lifecycle_events")
