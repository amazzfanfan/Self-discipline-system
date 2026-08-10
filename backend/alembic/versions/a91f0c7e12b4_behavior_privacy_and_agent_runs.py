"""behavior loop, privacy, and durable Agent runs

Revision ID: a91f0c7e12b4
Revises: f41a8c0d92e1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a91f0c7e12b4"
down_revision: Union[str, Sequence[str], None] = "f41a8c0d92e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE taskstatusenum ADD VALUE IF NOT EXISTS 'deferred'")

    op.add_column("tasks", sa.Column("rationale", sa.Text()))
    op.add_column("tasks", sa.Column("estimated_minutes", sa.String(20)))
    op.add_column("tasks", sa.Column("user_feedback", sa.String(30)))
    op.add_column("tasks", sa.Column("source", sa.String(30), server_default="adaptive"))
    op.create_index("ix_tasks_user_date_status", "tasks", ["user_id", "scheduled_date", "status"])

    op.add_column("user_profiles", sa.Column("daily_task_budget", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("user_profiles", sa.Column("memory_enabled", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("user_profiles", sa.Column("notification_settings", sa.JSON(), nullable=False, server_default="{}"))

    op.add_column("goals", sa.Column("target_metric", sa.String(100)))
    op.add_column("goals", sa.Column("target_value", sa.Float()))
    op.add_column("goals", sa.Column("current_value", sa.Float()))
    op.add_column("goals", sa.Column("deadline", sa.Date()))
    op.add_column("goals", sa.Column("milestones", sa.JSON(), nullable=False, server_default="[]"))

    op.create_table(
        "daily_checkins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("checkin_date", sa.Date(), nullable=False),
        sa.Column("sleep_hours", sa.Numeric(3, 1)),
        sa.Column("energy", sa.Integer(), nullable=False),
        sa.Column("mood", sa.Integer(), nullable=False),
        sa.Column("stress", sa.Integer(), nullable=False),
        sa.Column("available_minutes", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "checkin_date", name="uq_daily_checkins_user_date"),
    )
    op.create_index("ix_daily_checkins_user_id", "daily_checkins", ["user_id"])
    op.create_index("ix_daily_checkins_checkin_date", "daily_checkins", ["checkin_date"])

    op.create_table(
        "weekly_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("next_week_plan", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "week_start", name="uq_weekly_reviews_user_week"),
    )
    op.create_index("ix_weekly_reviews_user_id", "weekly_reviews", ["user_id"])
    op.create_index("ix_weekly_reviews_week_start", "weekly_reviews", ["week_start"])

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("user_message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default="running"),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("planner_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_agent_runs_run_id", "agent_runs", ["run_id"], unique=True)
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.create_table(
        "agent_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("tool_name", sa.String(100)),
        sa.Column("success", sa.String(10)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_steps_agent_run_id", "agent_steps", ["agent_run_id"])

    op.create_table(
        "pending_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_id", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="SET NULL")),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("original_request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pending_actions_action_id", "pending_actions", ["action_id"], unique=True)
    op.create_index("ix_pending_actions_user_id", "pending_actions", ["user_id"])
    op.create_index("ix_pending_actions_status", "pending_actions", ["status"])

    op.execute("UPDATE user_scores SET score = baseline_score")
    op.execute("""
        DELETE FROM user_scores duplicate
        USING user_scores keep
        WHERE duplicate.user_id = keep.user_id
          AND duplicate.dimension = keep.dimension
          AND duplicate.id::text > keep.id::text
    """)
    op.create_unique_constraint("uq_user_scores_user_dimension", "user_scores", ["user_id", "dimension"])
    op.create_index("ix_score_history_user_dimension_created", "score_history", ["user_id", "dimension", "created_at"])

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX IF NOT EXISTS ix_memories_content_trgm ON memories USING gin (content gin_trgm_ops)")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_am WHERE amname = 'hnsw') THEN
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw ON memories USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL';
                EXECUTE 'CREATE INDEX IF NOT EXISTS ix_goals_embedding_hnsw ON goals USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL';
            END IF;
        END $$
    """)

    for column in ("avatar_url", "portrait_photo_url", "front_photo_url", "side_photo_url"):
        op.execute(
            f"UPDATE user_profiles SET {column} = replace({column}, '/uploads/', '/api/users/me/photos/files/') "
            f"WHERE {column} LIKE '/uploads/%'"
        )
    op.execute(
        "UPDATE users SET avatar_url = replace(avatar_url, '/uploads/', '/api/users/me/photos/files/') "
        "WHERE avatar_url LIKE '/uploads/%'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_goals_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_memories_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_memories_content_trgm")
    op.drop_index("ix_score_history_user_dimension_created", table_name="score_history")
    op.drop_constraint("uq_user_scores_user_dimension", "user_scores", type_="unique")
    op.drop_table("pending_actions")
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
    op.drop_table("weekly_reviews")
    op.drop_table("daily_checkins")
    for column in ("milestones", "deadline", "current_value", "target_value", "target_metric"):
        op.drop_column("goals", column)
    for column in ("notification_settings", "memory_enabled", "daily_task_budget"):
        op.drop_column("user_profiles", column)
    op.drop_index("ix_tasks_user_date_status", table_name="tasks")
    for column in ("source", "user_feedback", "estimated_minutes", "rationale"):
        op.drop_column("tasks", column)
