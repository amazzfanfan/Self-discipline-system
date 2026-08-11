"""upgrade task scheduling semantics

Revision ID: b43d8e6a2f19
Revises: a91f0c7e12b4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b43d8e6a2f19"
down_revision: Union[str, Sequence[str], None] = "a91f0c7e12b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("disposition", sa.String(20)))
    op.add_column("tasks", sa.Column("disposition_reason", sa.String(200)))
    op.add_column("tasks", sa.Column("deferred_until", sa.DateTime(timezone=True)))
    op.add_column(
        "tasks",
        sa.Column("defer_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("tasks", sa.Column("original_scheduled_date", sa.Date()))
    op.create_index("ix_tasks_deferred_until", "tasks", ["deferred_until"])

    # Legacy pending tasks were never finalized. Excuse them during the upgrade
    # instead of retrospectively lowering users' adherence because of that bug.
    op.execute(
        """
        UPDATE tasks
        SET status = 'deferred',
            disposition = 'excused',
            disposition_reason = '系统升级前未结算任务，已自动免除'
        WHERE scheduled_date < CURRENT_DATE
          AND status IN ('pending', 'in_progress')
        """
    )
    op.execute(
        """
        UPDATE tasks
        SET disposition = 'excused',
            disposition_reason = COALESCE(disposition_reason, '旧版今日暂缓任务')
        WHERE status = 'deferred'
          AND disposition IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_deferred_until", table_name="tasks")
    op.drop_column("tasks", "original_scheduled_date")
    op.drop_column("tasks", "defer_count")
    op.drop_column("tasks", "deferred_until")
    op.drop_column("tasks", "disposition_reason")
    op.drop_column("tasks", "disposition")
