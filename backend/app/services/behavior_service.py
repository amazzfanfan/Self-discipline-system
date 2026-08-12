from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_today
from app.models.behavior import DailyCheckIn, WeeklyReview
from app.models.score import DimensionEnum, UserScore
from app.models.task import Task, TaskStatusEnum
from app.services.goal_progress_service import build_goal_progress_summaries


def current_week_start():
    today = local_today()
    return today - timedelta(days=today.weekday())


def last_completed_week_start(reference_date: date | None = None) -> date:
    today = reference_date or local_today()
    return today - timedelta(days=today.weekday() + 7)


async def calculate_behavior_metrics(db: AsyncSession, user_id) -> dict:
    today = local_today()
    start_28 = today - timedelta(days=27)
    result = await db.execute(
        select(Task).where(
            and_(Task.user_id == user_id, Task.scheduled_date >= start_28, Task.scheduled_date <= today)
        )
    )
    tasks = result.scalars().all()

    def window_stats(days: int, dimension: DimensionEnum | None = None) -> dict:
        start = today - timedelta(days=days - 1)
        eligible = [
            task for task in tasks
            if task.scheduled_date >= start
            and task.status in {TaskStatusEnum.completed, TaskStatusEnum.failed}
            and (dimension is None or task.dimension == dimension)
        ]
        sample_count = len(eligible)
        adherence = (
            round(100 * sum(task.status == TaskStatusEnum.completed for task in eligible) / sample_count, 1)
            if sample_count
            else None
        )
        confidence = (
            "none" if sample_count == 0
            else "low" if sample_count < 4
            else "medium" if sample_count < 8
            else "high"
        )
        return {
            "adherence": adherence,
            "sample_count": sample_count,
            "confidence": confidence,
        }

    def momentum_for(short_window: dict, long_window: dict) -> float | None:
        short_rate = short_window["adherence"]
        long_rate = long_window["adherence"]
        if short_rate is None and long_rate is None:
            return None
        if short_rate is None:
            return float(long_rate)
        if long_rate is None:
            return float(short_rate)
        return round(min(100.0, 0.65 * short_rate + 0.35 * long_rate), 1)

    score_result = await db.execute(select(UserScore).where(UserScore.user_id == user_id))
    scores = score_result.scalars().all()
    dimensions = {}
    for score in scores:
        stats_7d = window_stats(7, score.dimension)
        stats_28d = window_stats(28, score.dimension)
        momentum = momentum_for(stats_7d, stats_28d)
        dimensions[score.dimension.value] = {
            "baseline": float(score.baseline_score),
            "adherence_7d": stats_7d["adherence"],
            "adherence_28d": stats_28d["adherence"],
            "sample_count_7d": stats_7d["sample_count"],
            "sample_count_28d": stats_28d["sample_count"],
            "confidence": stats_28d["confidence"],
            "momentum": momentum,
            "streak_days": score.streak_days,
        }
    overall_7d = window_stats(7)
    overall_28d = window_stats(28)
    dimension_momentum = [
        item["momentum"] for item in dimensions.values() if item["momentum"] is not None
    ]
    return {
        "overall": {
            "adherence_7d": overall_7d["adherence"],
            "adherence_28d": overall_28d["adherence"],
            "sample_count_7d": overall_7d["sample_count"],
            "sample_count_28d": overall_28d["sample_count"],
            "confidence": overall_28d["confidence"],
            "momentum": (
                round(sum(dimension_momentum) / len(dimension_momentum), 1)
                if dimension_momentum
                else None
            ),
        },
        "dimensions": dimensions,
    }


async def build_weekly_review(
    db: AsyncSession,
    user_id,
    week_start: date | None = None,
) -> WeeklyReview:
    week_start = week_start or last_completed_week_start()
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
    goal_progress_map = await build_goal_progress_summaries(
        db,
        user_id,
        period_start=week_start,
        period_end=week_end,
        as_of=week_end,
    )
    goal_progress = [
        item
        for item in goal_progress_map.values()
        if item["scheduled_total"] > 0 or item["completed"] > 0
    ]
    goal_scheduled = sum(item["scheduled_to_date"] for item in goal_progress)
    goal_completed = sum(item["completed"] for item in goal_progress)
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
        "goal_progress": goal_progress,
        "goal_scheduled": goal_scheduled,
        "goal_completed": goal_completed,
        "goal_adherence": (
            round(min(100.0, 100 * goal_completed / goal_scheduled), 1)
            if goal_scheduled
            else None
        ),
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
