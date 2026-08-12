from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.time import app_timezone, local_today
from app.models.goal import Goal, GoalProgressEvent
from app.models.task import Task


def _date_value(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(app_timezone()).date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def expected_goal_occurrences(goal, start: date, end: date) -> int:
    """Count scheduled occurrences, bounded by goal lifetime."""
    if end < start:
        return 0
    goal_start = _date_value(getattr(goal, "start_date", None)) or _date_value(
        getattr(goal, "created_at", None)
    )
    deadline = _date_value(getattr(goal, "deadline", None))
    if goal_start:
        start = max(start, goal_start)
    if deadline:
        end = min(end, deadline)
    if end < start:
        return 0
    recurrence = getattr(goal, "recurrence", None) or "flexible"
    if recurrence == "flexible":
        return 0
    if recurrence == "daily":
        return (end - start).days + 1
    days = set(getattr(goal, "days_of_week", None) or [])
    return sum(
        (start + timedelta(days=offset)).weekday() in days
        for offset in range((end - start).days + 1)
    )


async def record_goal_task_completion(db, task: Task) -> dict | None:
    """Idempotently turn a linked task completion into goal progress."""
    if not getattr(task, "goal_id", None):
        return None
    goal = await db.scalar(
        select(Goal)
        .where(Goal.id == task.goal_id, Goal.user_id == task.user_id)
        .with_for_update()
    )
    if not goal:
        return None
    # The goal row lock serializes progress changes. Rechecking the immutable
    # evidence after acquiring it makes retries and concurrent completions safe.
    existing = await db.scalar(
        select(GoalProgressEvent).where(
            GoalProgressEvent.goal_id == task.goal_id,
            GoalProgressEvent.task_id == task.id,
            GoalProgressEvent.event_type == "task_completed",
        )
    )
    if existing:
        return {
            "goal_id": str(existing.goal_id),
            "delta": existing.delta,
            "current_value": existing.current_value,
            "already_recorded": True,
        }
    previous_value = float(goal.current_value or 0)
    goal.completed_sessions = (goal.completed_sessions or 0) + 1
    if (goal.progress_mode or "sessions") == "sessions":
        goal.current_value = previous_value + 1
    current_value = float(goal.current_value or previous_value)
    goal.last_progress_at = datetime.now(timezone.utc)
    event = GoalProgressEvent(
        goal_id=goal.id,
        user_id=goal.user_id,
        task_id=task.id,
        event_type="task_completed",
        delta=1,
        previous_value=previous_value,
        current_value=current_value,
        event_date=task.scheduled_date,
        source="task_completion",
        event_metadata={
            "task_title": task.title,
            "dimension": (
                task.dimension.value
                if hasattr(task.dimension, "value")
                else str(task.dimension)
            ),
        },
    )
    db.add(event)
    return {
        "goal_id": str(goal.id),
        "delta": 1,
        "current_value": current_value,
        "completed_sessions": goal.completed_sessions,
        "target_value": goal.target_value,
        "already_recorded": False,
    }


async def record_manual_goal_progress(
    db,
    goal: Goal,
    *,
    previous_value: float | None,
    current_value: float | None,
    source: str = "goal_update",
) -> GoalProgressEvent | None:
    if previous_value == current_value:
        return None
    previous = float(previous_value or 0)
    current = float(current_value or 0)
    event = GoalProgressEvent(
        goal_id=goal.id,
        user_id=goal.user_id,
        event_type="manual_progress",
        delta=current - previous,
        previous_value=previous,
        current_value=current,
        event_date=local_today(),
        source=source,
        event_metadata={},
    )
    goal.last_progress_at = datetime.now(timezone.utc)
    db.add(event)
    return event


async def build_goal_progress_summaries(
    db,
    user_id,
    *,
    period_start: date,
    period_end: date,
    as_of: date | None = None,
) -> dict[str, dict]:
    goals = (
        await db.execute(select(Goal).where(Goal.user_id == user_id))
    ).scalars().all()
    if not goals:
        return {}
    goal_ids = [goal.id for goal in goals]
    events = (
        await db.execute(
            select(GoalProgressEvent).where(
                GoalProgressEvent.goal_id.in_(goal_ids),
                GoalProgressEvent.event_type == "task_completed",
                GoalProgressEvent.event_date >= period_start,
                GoalProgressEvent.event_date <= period_end,
            )
        )
    ).scalars().all()
    completed_by_goal: dict = defaultdict(int)
    for event in events:
        completed_by_goal[event.goal_id] += 1

    flexible_tasks = (
        await db.execute(
            select(Task).where(
                Task.goal_id.in_(goal_ids),
                Task.scheduled_date >= period_start,
                Task.scheduled_date <= period_end,
            )
        )
    ).scalars().all()
    planned_dates_by_goal: dict = defaultdict(set)
    for task in flexible_tasks:
        planned_dates_by_goal[task.goal_id].add(task.scheduled_date)

    effective_as_of = min(as_of or local_today(), period_end)
    summaries = {}
    for goal in goals:
        scheduled_total = expected_goal_occurrences(goal, period_start, period_end)
        scheduled_to_date = expected_goal_occurrences(
            goal, period_start, effective_as_of
        )
        if (goal.recurrence or "flexible") == "flexible":
            dates = planned_dates_by_goal[goal.id]
            scheduled_total = len(dates)
            scheduled_to_date = sum(item <= effective_as_of for item in dates)
        completed = completed_by_goal[goal.id]
        adherence = (
            round(min(100.0, 100 * completed / scheduled_to_date), 1)
            if scheduled_to_date
            else None
        )
        summaries[str(goal.id)] = {
            "goal_id": str(goal.id),
            "content": goal.content,
            "goal_type": goal.goal_type,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "scheduled_total": scheduled_total,
            "scheduled_to_date": scheduled_to_date,
            "completed": completed,
            "remaining_to_date": max(0, scheduled_to_date - completed),
            "adherence": adherence,
            "completed_sessions": goal.completed_sessions or 0,
            "current_value": goal.current_value,
            "target_value": goal.target_value,
            "progress_mode": goal.progress_mode or "sessions",
        }
    return summaries


async def get_goal_progress_timeline(db, user_id, goal_id, *, limit: int = 30):
    goal = await db.scalar(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    if not goal:
        return None
    events = (
        await db.execute(
            select(GoalProgressEvent)
            .where(GoalProgressEvent.goal_id == goal.id)
            .order_by(GoalProgressEvent.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "delta": event.delta,
            "previous_value": event.previous_value,
            "current_value": event.current_value,
            "event_date": event.event_date.isoformat(),
            "source": event.source,
            "metadata": event.event_metadata or {},
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]
