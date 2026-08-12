"""add per-subscription push delivery attempts

Revision ID: d13c8f2a714e
Revises: b1824f09d1ef
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d13c8f2a714e"
down_revision: str | Sequence[str] | None = "b1824f09d1ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["user_notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["push_subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id",
            "subscription_id",
            name="uq_push_deliveries_notification_subscription",
        ),
    )
    for column in ("notification_id", "subscription_id", "user_id", "status", "next_attempt_at"):
        op.create_index(f"ix_push_deliveries_{column}", "push_deliveries", [column])


def downgrade() -> None:
    op.drop_table("push_deliveries")
