"""add deterministic assessment runs

Revision ID: f41a8c0d92e1
Revises: d7b32c16a842
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f41a8c0d92e1"
down_revision: Union[str, Sequence[str], None] = "d7b32c16a842"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_scores",
        sa.Column("baseline_score", sa.Numeric(4, 1), nullable=False, server_default="50.0"),
    )
    op.execute("UPDATE user_scores SET baseline_score = score")
    op.create_table(
        "assessment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("rubric_version", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.JSON(), nullable=False),
        sa.Column("overall_confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("skin_source", sa.String(length=32), nullable=False),
        sa.Column("skin_input_hash", sa.String(length=64), nullable=True),
        sa.Column("reused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "input_hash",
            "rubric_version",
            name="uq_assessment_run_user_input_version",
        ),
    )
    op.create_index("ix_assessment_runs_user_id", "assessment_runs", ["user_id"])
    op.create_index("ix_assessment_runs_input_hash", "assessment_runs", ["input_hash"])


def downgrade() -> None:
    op.drop_index("ix_assessment_runs_input_hash", table_name="assessment_runs")
    op.drop_index("ix_assessment_runs_user_id", table_name="assessment_runs")
    op.drop_table("assessment_runs")
    op.drop_column("user_scores", "baseline_score")
