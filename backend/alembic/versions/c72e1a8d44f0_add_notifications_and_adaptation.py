"""add persistent notifications and task adaptation evidence

Revision ID: c72e1a8d44f0
Revises: b43d8e6a2f19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c72e1a8d44f0"
down_revision: Union[str, Sequence[str], None] = "b43d8e6a2f19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "adaptation_metadata",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.create_table(
        "user_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_user_notifications_dedupe"),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.create_index("ix_user_notifications_created_at", "user_notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_notifications_created_at", table_name="user_notifications")
    op.drop_index("ix_user_notifications_user_id", table_name="user_notifications")
    op.drop_table("user_notifications")
    op.drop_column("tasks", "adaptation_metadata")

