"""add structured goal schedules

Revision ID: c7a0f96d2e11
Revises: f35c9a12d807
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7a0f96d2e11"
down_revision: Union[str, Sequence[str], None] = "f35c9a12d807"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "goals",
        sa.Column(
            "recurrence",
            sa.String(20),
            nullable=False,
            server_default="flexible",
        ),
    )
    op.add_column(
        "goals",
        sa.Column(
            "days_of_week",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column("goals", sa.Column("preferred_time", sa.Time()))
    op.add_column("goals", sa.Column("duration_minutes", sa.Integer()))
    op.add_column("goals", sa.Column("start_date", sa.Date()))
    op.add_column(
        "goals",
        sa.Column(
            "reminder_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "goals",
        sa.Column(
            "reminder_minutes_before",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column("goal_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("tasks", sa.Column("scheduled_time", sa.Time()))
    op.create_foreign_key(
        "fk_tasks_goal_id_goals",
        "tasks",
        "goals",
        ["goal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tasks_goal_id", "tasks", ["goal_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_goal_id", table_name="tasks")
    op.drop_constraint("fk_tasks_goal_id_goals", "tasks", type_="foreignkey")
    op.drop_column("tasks", "scheduled_time")
    op.drop_column("tasks", "goal_id")
    op.drop_column("goals", "reminder_minutes_before")
    op.drop_column("goals", "reminder_enabled")
    op.drop_column("goals", "start_date")
    op.drop_column("goals", "duration_minutes")
    op.drop_column("goals", "preferred_time")
    op.drop_column("goals", "days_of_week")
    op.drop_column("goals", "recurrence")
