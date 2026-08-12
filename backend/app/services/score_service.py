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


async def rebuild_behavior_counters(
    db: AsyncSession,
    user_id: str,
    dimension: DimensionEnum,
) -> dict:
    """Recompute mutable behavior counters after a completion correction."""
    from app.models.task import Task, TaskStatusEnum

    score_record = await db.scalar(
        select(UserScore).where(
            UserScore.user_id == user_id,
            UserScore.dimension == dimension,
        )
    )
    tasks = (
        await db.execute(
            select(Task).where(Task.user_id == user_id, Task.dimension == dimension)
        )
    ).scalars().all()
    completed_dates = sorted(
        {task.scheduled_date for task in tasks if task.status == TaskStatusEnum.completed}
    )
    negative_tasks = [
        task
        for task in tasks
        if task.status == TaskStatusEnum.failed
        and task.disposition in {"skipped", "expired"}
    ]
    score_record.total_positive_count = len(completed_dates)
    score_record.total_negative_count = len(negative_tasks)
    score_record.last_completed_date = completed_dates[-1] if completed_dates else None

    streak = 0
    if completed_dates:
        last_completed = completed_dates[-1]
        if not any(task.scheduled_date >= last_completed for task in negative_tasks):
            streak = 1
            cursor = last_completed
            completed_set = set(completed_dates)
            while cursor - timedelta(days=1) in completed_set:
                cursor -= timedelta(days=1)
                streak += 1
    score_record.streak_days = streak
    score_record.last_score_change = datetime.now(timezone.utc)
    return {
        "dimension": dimension.value,
        "streak": streak,
        "completed_days": len(completed_dates),
        "missed_tasks": len(negative_tasks),
    }

