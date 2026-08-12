"""add goal progress events

Revision ID: b70a2c18f522
Revises: d819a66f3204
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b70a2c18f522"
down_revision: Union[str, Sequence[str], None] = "d819a66f3204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "goals",
        sa.Column(
            "progress_mode",
            sa.String(20),
            nullable=False,
            server_default="sessions",
        ),
    )
    op.add_column(
        "goals",
        sa.Column(
            "completed_sessions",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("goals", sa.Column("last_progress_at", sa.DateTime(timezone=True)))
    op.create_table(
        "goal_progress_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True)),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("previous_value", sa.Float()),
        sa.Column("current_value", sa.Float()),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="system"),
        sa.Column(
            "event_metadata",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "goal_id",
            "task_id",
            "event_type",
            name="uq_goal_progress_task_event",
        ),
    )
    op.create_index(
        "ix_goal_progress_goal_created",
        "goal_progress_events",
        ["goal_id", "created_at"],
    )
    op.create_index(
        "ix_goal_progress_user_date",
        "goal_progress_events",
        ["user_id", "event_date"],
    )

    # Preserve completed linked tasks as historical progress when upgrading.
    connection = op.get_bind()
    completed_tasks = connection.execute(
        sa.text(
            """
            SELECT id, goal_id, user_id, scheduled_date,
                   COALESCE(completed_at, created_at, now()) AS completed_at
            FROM tasks
            WHERE goal_id IS NOT NULL AND status::text = 'completed'
            """
        )
    ).mappings()
    progress_table = sa.table(
        "goal_progress_events",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("goal_id", postgresql.UUID(as_uuid=True)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
        sa.column("task_id", postgresql.UUID(as_uuid=True)),
        sa.column("event_type", sa.String()),
        sa.column("delta", sa.Float()),
        sa.column("event_date", sa.Date()),
        sa.column("source", sa.String()),
        sa.column("event_metadata", postgresql.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    rows = [
        {
            "id": uuid.uuid4(),
            "goal_id": item["goal_id"],
            "user_id": item["user_id"],
            "task_id": item["id"],
            "event_type": "task_completed",
            "delta": 1,
            "event_date": item["scheduled_date"],
            "source": "migration",
            "event_metadata": {},
            "created_at": item["completed_at"],
        }
        for item in completed_tasks
    ]
    if rows:
        op.bulk_insert(progress_table, rows)
    connection.execute(
        sa.text(
            """
            UPDATE goals g
            SET completed_sessions = counts.total,
                current_value = CASE
                    WHEN g.current_value IS NULL OR g.current_value = 0
                    THEN counts.total
                    ELSE g.current_value
                END,
                last_progress_at = counts.last_progress_at
            FROM (
                SELECT goal_id, count(*)::integer AS total,
                       max(created_at) AS last_progress_at
                FROM goal_progress_events
                WHERE event_type = 'task_completed'
                GROUP BY goal_id
            ) counts
            WHERE g.id = counts.goal_id
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_goal_progress_user_date", table_name="goal_progress_events")
    op.drop_index("ix_goal_progress_goal_created", table_name="goal_progress_events")
    op.drop_table("goal_progress_events")
    op.drop_column("goals", "last_progress_at")
    op.drop_column("goals", "completed_sessions")
    op.drop_column("goals", "progress_mode")
