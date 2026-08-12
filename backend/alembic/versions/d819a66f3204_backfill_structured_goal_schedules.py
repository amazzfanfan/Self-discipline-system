"""backfill structured goal schedules

Revision ID: d819a66f3204
Revises: c7a0f96d2e11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.services.goal_schedule_service import parse_goal_schedule


revision: str = "d819a66f3204"
down_revision: Union[str, Sequence[str], None] = "c7a0f96d2e11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    goals = sa.table(
        "goals",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("content", sa.Text()),
        sa.column("recurrence", sa.String()),
        sa.column("days_of_week", postgresql.JSON()),
        sa.column("preferred_time", sa.Time()),
        sa.column("duration_minutes", sa.Integer()),
        sa.column("reminder_enabled", sa.Boolean()),
    )
    rows = connection.execute(
        sa.select(
            goals.c.id,
            goals.c.content,
            goals.c.recurrence,
            goals.c.preferred_time,
            goals.c.duration_minutes,
        )
    ).mappings()
    for row in rows:
        parsed = parse_goal_schedule(row["content"])
        values = {}
        if row["recurrence"] == "flexible" and parsed.get("recurrence"):
            values["recurrence"] = parsed["recurrence"]
            values["days_of_week"] = parsed.get("days_of_week", [])
        if row["preferred_time"] is None and parsed.get("preferred_time"):
            values["preferred_time"] = parsed["preferred_time"]
            values["reminder_enabled"] = True
        if row["duration_minutes"] is None and parsed.get("duration_minutes"):
            values["duration_minutes"] = parsed["duration_minutes"]
        if values:
            connection.execute(
                goals.update().where(goals.c.id == row["id"]).values(**values)
            )


def downgrade() -> None:
    # Parsed values are user-visible planning data and intentionally retained.
    pass
