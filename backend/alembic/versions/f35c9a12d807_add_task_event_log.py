"""add task event log

Revision ID: f35c9a12d807
Revises: e21b4c8a60d2
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f35c9a12d807"
down_revision: Union[str, Sequence[str], None] = "e21b4c8a60d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(24)),
        sa.Column("to_status", sa.String(24)),
        sa.Column("reason", sa.String(200)),
        sa.Column("actor", sa.String(20), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
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
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_events_task_created", "task_events", ["task_id", "created_at"])
    op.create_index("ix_task_events_user_created", "task_events", ["user_id", "created_at"])

    connection = op.get_bind()
    existing_tasks = connection.execute(
        sa.text(
            """
            SELECT id, user_id, status::text, disposition, defer_count, created_at
            FROM tasks
            """
        )
    ).mappings()
    event_table = sa.table(
        "task_events",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("task_id", postgresql.UUID(as_uuid=True)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
        sa.column("event_type", sa.String()),
        sa.column("from_status", sa.String()),
        sa.column("to_status", sa.String()),
        sa.column("actor", sa.String()),
        sa.column("source", sa.String()),
        sa.column("event_metadata", postgresql.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    rows = [
        {
            "id": uuid.uuid4(),
            "task_id": item["id"],
            "user_id": item["user_id"],
            "event_type": "legacy_snapshot",
            "from_status": None,
            "to_status": item["status"],
            "actor": "system",
            "source": "migration",
            "event_metadata": {
                "disposition": item["disposition"],
                "defer_count": item["defer_count"] or 0,
            },
            "created_at": item["created_at"],
        }
        for item in existing_tasks
    ]
    if rows:
        op.bulk_insert(event_table, rows)


def downgrade() -> None:
    op.drop_index("ix_task_events_user_created", table_name="task_events")
    op.drop_index("ix_task_events_task_created", table_name="task_events")
    op.drop_table("task_events")
