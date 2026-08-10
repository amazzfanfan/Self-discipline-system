from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.score import UserScore, DimensionEnum


async def record_task_completion(db: AsyncSession, user_id: str, dimension: DimensionEnum) -> dict | None:
    """Record behavior without pretending it changes the user's health baseline."""
    result = await db.execute(
        select(UserScore).where(UserScore.user_id == user_id, UserScore.dimension == dimension)
    )
    score_record = result.scalar_one()

    score_record.streak_days += 1
    score_record.total_positive_count += 1

    score_record.last_score_change = datetime.now(timezone.utc)
    return {
        "dimension": dimension.value,
        "delta": 0.0,
        "streak": score_record.streak_days,
        "message": "已计入行为完成率和成长动量",
    }


async def record_negative(db: AsyncSession, user_id: str, dimension: DimensionEnum, reason: str) -> dict:
    """Record a missed behavior without deducting the assessment baseline."""
    result = await db.execute(
        select(UserScore).where(UserScore.user_id == user_id, UserScore.dimension == dimension)
    )
    score_record = result.scalar_one()

    score_record.streak_days = 0
    score_record.total_negative_count += 1
    score_record.last_score_change = datetime.now(timezone.utc)

    return {"dimension": dimension.value, "delta": 0.0, "reason": reason}

