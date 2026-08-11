from collections import defaultdict
from datetime import timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_today
from app.models.behavior import DailyCheckIn, WeeklyReview
from app.models.score import DimensionEnum, UserScore
from app.models.task import Task, TaskStatusEnum


def current_week_start():
    today = local_today()
    return today - timedelta(days=today.weekday())


async def calculate_behavior_metrics(db: AsyncSession, user_id) -> dict:
    today = local_today()
    start_28 = today - timedelta(days=27)
    result = await db.execute(
        select(Task).where(
            and_(Task.user_id == user_id, Task.scheduled_date >= start_28, Task.scheduled_date <= today)
        )
    )
    tasks = result.scalars().all()

    def rate(days: int, dimension: DimensionEnum | None = None) -> float:
        start = today - timedelta(days=days - 1)
        eligible = [
            task for task in tasks
            if task.scheduled_date >= start
            and task.status in {TaskStatusEnum.completed, TaskStatusEnum.failed}
            and (dimension is None or task.dimension == dimension)
        ]
        if not eligible:
            return 0.0
        return round(100 * sum(task.status == TaskStatusEnum.completed for task in eligible) / len(eligible), 1)

    score_result = await db.execute(select(UserScore).where(UserScore.user_id == user_id))
    scores = score_result.scalars().all()
    dimensions = {}
    for score in scores:
        adherence_7d = rate(7, score.dimension)
        adherence_28d = rate(28, score.dimension)
        momentum = round(min(100.0, 0.65 * adherence_7d + 0.35 * adherence_28d), 1)
        dimensions[score.dimension.value] = {
            "baseline": float(score.baseline_score),
            "adherence_7d": adherence_7d,
            "adherence_28d": adherence_28d,
            "momentum": momentum,
            "streak_days": score.streak_days,
        }
    return {
        "overall": {
            "adherence_7d": rate(7),
            "adherence_28d": rate(28),
            "momentum": round(
                sum(item["momentum"] for item in dimensions.values()) / max(len(dimensions), 1), 1
            ),
        },
        "dimensions": dimensions,
    }


async def build_weekly_review(db: AsyncSession, user_id) -> WeeklyReview:
    week_start = current_week_start()
    week_end = week_start + timedelta(days=6)
    task_result = await db.execute(
        select(Task).where(
            and_(Task.user_id == user_id, Task.scheduled_date >= week_start, Task.scheduled_date <= week_end)
        )
    )
    tasks = task_result.scalars().all()
    by_dimension: dict[str, dict[str, int]] = defaultdict(lambda: {"completed": 0, "planned": 0})
    for task in tasks:
        if task.status in {TaskStatusEnum.completed, TaskStatusEnum.failed}:
            item = by_dimension[task.dimension.value]
            item["planned"] += 1
            item["completed"] += int(task.status == TaskStatusEnum.completed)

    checkin_result = await db.execute(
        select(DailyCheckIn).where(
            and_(DailyCheckIn.user_id == user_id, DailyCheckIn.checkin_date >= week_start, DailyCheckIn.checkin_date <= week_end)
        )
    )
    checkins = checkin_result.scalars().all()
    dimension_rates = {
        key: round(100 * value["completed"] / value["planned"], 1) if value["planned"] else 0.0
        for key, value in by_dimension.items()
    }
    weakest = min(dimension_rates, key=dimension_rates.get) if dimension_rates else None
    summary = {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "completed_tasks": sum(task.status == TaskStatusEnum.completed for task in tasks),
        "planned_tasks": sum(task.status in {TaskStatusEnum.completed, TaskStatusEnum.failed} for task in tasks),
        "excused_tasks": sum(task.disposition == "excused" for task in tasks),
        "rescheduled_tasks": sum(task.disposition == "rescheduled" for task in tasks),
        "expired_tasks": sum(task.disposition == "expired" for task in tasks),
        "skipped_tasks": sum(task.disposition == "skipped" for task in tasks),
        "dimension_adherence": dimension_rates,
        "checkin_days": len(checkins),
        "average_energy": round(sum(item.energy for item in checkins) / len(checkins), 1) if checkins else None,
        "average_stress": round(sum(item.stress for item in checkins) / len(checkins), 1) if checkins else None,
        "suggested_focus": weakest,
    }
    existing_result = await db.execute(
        select(WeeklyReview).where(WeeklyReview.user_id == user_id, WeeklyReview.week_start == week_start)
    )
    review = existing_result.scalar_one_or_none()
    if review:
        review.summary = summary
    else:
        review = WeeklyReview(user_id=user_id, week_start=week_start, summary=summary, next_week_plan={})
        db.add(review)
    await db.flush()
    return review
