"""allow multiple goal tasks per dimension and day

Revision ID: c41e8d2a750f
Revises: a62d4e91b730
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c41e8d2a750f"
down_revision: Union[str, Sequence[str], None] = "a62d4e91b730"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_tasks_user_dimension_date", "tasks", type_="unique")
    op.create_index(
        "uq_tasks_user_goal_date",
        "tasks",
        ["user_id", "goal_id", "scheduled_date"],
        unique=True,
        postgresql_where=sa.text("goal_id IS NOT NULL"),
    )
    op.create_index(
        "uq_tasks_user_baseline_dimension_date",
        "tasks",
        ["user_id", "dimension", "scheduled_date"],
        unique=True,
        postgresql_where=sa.text("goal_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tasks_user_baseline_dimension_date", table_name="tasks")
    op.drop_index("uq_tasks_user_goal_date", table_name="tasks")
    op.create_unique_constraint(
        "uq_tasks_user_dimension_date",
        "tasks",
        ["user_id", "dimension", "scheduled_date"],
    )
