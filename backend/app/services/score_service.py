from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.score import UserScore, ScoreHistory, DimensionEnum


THRESHOLDS = {
    DimensionEnum.exercise: 7,
    DimensionEnum.diet: 5,
    DimensionEnum.sleep: 7,
    DimensionEnum.appearance: 14,
}


async def record_task_completion(db: AsyncSession, user_id: str, dimension: DimensionEnum) -> dict | None:
    """Record task completion, check if score threshold is met. Returns score change info or None."""
    result = await db.execute(
        select(UserScore).where(UserScore.user_id == user_id, UserScore.dimension == dimension)
    )
    score_record = result.scalar_one()

    score_record.streak_days += 1
    score_record.total_positive_count += 1

    threshold = THRESHOLDS[dimension]
    if score_record.streak_days >= threshold and score_record.streak_days % threshold == 0:
        score_record.score = min(100, float(score_record.score) + 0.1)
        score_record.last_score_change = datetime.now(timezone.utc)

        history = ScoreHistory(
            user_id=user_id,
            dimension=dimension,
            delta=0.1,
            reason=f"连续{score_record.streak_days}天完成{dimension.value}任务",
        )
        db.add(history)
        return {"dimension": dimension.value, "delta": 0.1, "streak": score_record.streak_days}

    return None


async def record_negative(db: AsyncSession, user_id: str, dimension: DimensionEnum, reason: str) -> dict:
    """Record negative behavior, deduct score."""
    result = await db.execute(
        select(UserScore).where(UserScore.user_id == user_id, UserScore.dimension == dimension)
    )
    score_record = result.scalar_one()

    score_record.score = max(0, float(score_record.score) - 0.1)
    score_record.streak_days = 0
    score_record.total_negative_count += 1
    score_record.last_score_change = datetime.now(timezone.utc)

    history = ScoreHistory(
        user_id=user_id,
        dimension=dimension,
        delta=-0.1,
        reason=reason,
    )
    db.add(history)
    return {"dimension": dimension.value, "delta": -0.1}

