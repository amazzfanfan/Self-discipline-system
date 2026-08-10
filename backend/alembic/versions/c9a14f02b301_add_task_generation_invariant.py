"""add task generation invariant

Revision ID: c9a14f02b301
Revises: 31cf1d26508c
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c9a14f02b301"
down_revision: Union[str, Sequence[str], None] = "31cf1d26508c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the earliest task when legacy scheduler races already created duplicates.
    op.execute(
        """
        DELETE FROM tasks
        WHERE ctid IN (
          SELECT ctid
          FROM (
            SELECT ctid,
                   row_number() OVER (
                     PARTITION BY user_id, dimension, scheduled_date
                     ORDER BY created_at, id
                   ) AS duplicate_number
            FROM tasks
          ) duplicates
          WHERE duplicate_number > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_tasks_user_dimension_date",
        "tasks",
        ["user_id", "dimension", "scheduled_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_tasks_user_dimension_date", "tasks", type_="unique"
    )
