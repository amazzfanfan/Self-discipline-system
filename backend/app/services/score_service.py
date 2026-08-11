from datetime import date, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.score import UserScore, DimensionEnum
from app.core.time import local_today


async def record_task_completion(
    db: AsyncSession,
    user_id: str,
    dimension: DimensionEnum,
    completion_date: date | None = None,
) -> dict | None:
    """Record behavior without pretending it changes the user's health baseline."""
    result = await db.execute(
        select(UserScore).where(UserScore.user_id == user_id, UserScore.dimension == dimension)
    )
    score_record = result.scalar_one()

    completed_on = completion_date or local_today()
    is_new_completion_day = score_record.last_completed_date != completed_on
    if score_record.last_completed_date == completed_on:
        pass
    elif score_record.last_completed_date == completed_on - timedelta(days=1):
        score_record.streak_days += 1
    else:
        score_record.streak_days = 1
    score_record.last_completed_date = completed_on
    if is_new_completion_day:
        score_record.total_positive_count += 1

    score_record.last_score_change = datetime.now(timezone.utc)
    return {
        "dimension": dimension.value,
        "delta": 0.0,
        "streak": score_record.streak_days,
        "message": "已计入行为完成率和成长动量",
    }


async def record_negative(
    db: AsyncSession,
    user_id: str,
    dimension: DimensionEnum,
    reason: str,
    event_date: date | None = None,
) -> dict:
    """Record a missed behavior without deducting the assessment baseline."""
    result = await db.execute(
        select(UserScore).where(UserScore.user_id == user_id, UserScore.dimension == dimension)
    )
    score_record = result.scalar_one()

    missed_on = event_date or local_today()
    if score_record.last_completed_date is None or missed_on >= score_record.last_completed_date:
        score_record.streak_days = 0
    score_record.total_negative_count += 1
    score_record.last_score_change = datetime.now(timezone.utc)

    return {"dimension": dimension.value, "delta": 0.0, "reason": reason}

