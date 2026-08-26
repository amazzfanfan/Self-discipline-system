"""add conversation summaries

Revision ID: a8c9d0e1f2b3
Revises: f7b1c2d3e4a5
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a8c9d0e1f2b3"
down_revision: str | Sequence[str] | None = "f7b1c2d3e4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("through_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("through_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summarized_message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.String(length=40), nullable=False, server_default="conversation-summary-v1"),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["through_message_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_conversation_summaries_user"),
    )
    op.create_index(
        "ix_conversation_summaries_user_id",
        "conversation_summaries",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("conversation_summaries")
