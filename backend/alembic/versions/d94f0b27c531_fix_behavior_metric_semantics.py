"""fix behavior metric semantics

Revision ID: d94f0b27c531
Revises: c72e1a8d44f0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d94f0b27c531"
down_revision: Union[str, Sequence[str], None] = "c72e1a8d44f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_scores", sa.Column("last_completed_date", sa.Date()))
    op.execute(
        """
        WITH completed_days AS (
            SELECT
                user_id,
                dimension,
                scheduled_date,
                ROW_NUMBER() OVER (
                    PARTITION BY user_id, dimension
                    ORDER BY scheduled_date DESC
                ) AS sequence_number,
                MAX(scheduled_date) OVER (
                    PARTITION BY user_id, dimension
                ) AS latest_date
            FROM tasks
            WHERE status = 'completed'
        ), streaks AS (
            SELECT
                user_id,
                dimension,
                MAX(latest_date) AS last_completed_date,
                COUNT(*) FILTER (
                    WHERE latest_date - scheduled_date = sequence_number - 1
                ) AS streak_days
            FROM completed_days
            GROUP BY user_id, dimension
        )
        UPDATE user_scores AS score
        SET
            last_completed_date = streak.last_completed_date,
            streak_days = streak.streak_days
        FROM streaks AS streak
        WHERE score.user_id = streak.user_id
          AND score.dimension = streak.dimension
        """
    )


def downgrade() -> None:
    op.drop_column("user_scores", "last_completed_date")
