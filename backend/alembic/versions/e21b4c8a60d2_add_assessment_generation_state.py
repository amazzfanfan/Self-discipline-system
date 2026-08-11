"""add assessment generation state

Revision ID: e21b4c8a60d2
Revises: d94f0b27c531
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e21b4c8a60d2"
down_revision: Union[str, Sequence[str], None] = "d94f0b27c531"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assessment_runs",
        sa.Column("generation_status", sa.String(24), nullable=False, server_default="completed"),
    )
    op.add_column(
        "assessment_runs",
        sa.Column("generation_stage", sa.String(32), nullable=False, server_default="completed"),
    )
    op.add_column("assessment_runs", sa.Column("generation_error", sa.String(120)))
    op.add_column(
        "assessment_runs",
        sa.Column(
            "care_suggestions",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "assessment_runs",
        sa.Column("profile_message_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("assessment_runs", sa.Column("generation_started_at", sa.DateTime(timezone=True)))
    op.add_column("assessment_runs", sa.Column("generation_completed_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_assessment_runs_profile_message",
        "assessment_runs",
        "conversations",
        ["profile_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("assessment_runs", "generation_status", server_default="pending")
    op.alter_column("assessment_runs", "generation_stage", server_default="queued")


def downgrade() -> None:
    op.drop_constraint(
        "fk_assessment_runs_profile_message",
        "assessment_runs",
        type_="foreignkey",
    )
    op.drop_column("assessment_runs", "generation_completed_at")
    op.drop_column("assessment_runs", "generation_started_at")
    op.drop_column("assessment_runs", "profile_message_id")
    op.drop_column("assessment_runs", "care_suggestions")
    op.drop_column("assessment_runs", "generation_error")
    op.drop_column("assessment_runs", "generation_stage")
    op.drop_column("assessment_runs", "generation_status")
