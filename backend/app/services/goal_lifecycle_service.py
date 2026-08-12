from __future__ import annotations

from datetime import datetime, timezone

from app.models.goal import Goal, GoalLifecycleEvent, GoalStatus


TRACKED_FIELDS = (
    "content",
    "goal_type",
    "status",
    "target_metric",
    "target_value",
    "current_value",
    "progress_mode",
    "deadline",
    "recurrence",
    "days_of_week",
    "preferred_time",
    "duration_minutes",
    "start_date",
    "reminder_enabled",
    "reminder_minutes_before",
)


def _serialize(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def goal_lifecycle_snapshot(goal: Goal) -> dict:
    return {field: _serialize(getattr(goal, field, None)) for field in TRACKED_FIELDS}


def record_goal_lifecycle_event(
    db,
    goal: Goal,
    *,
    event_type: str,
    previous_state: dict | None = None,
    new_state: dict | None = None,
    reason: str | None = None,
    actor: str = "user",
    source: str = "api",
) -> GoalLifecycleEvent:
    event = GoalLifecycleEvent(
        goal_id=goal.id,
        user_id=goal.user_id,
        event_type=event_type,
        previous_state=previous_state or {},
        new_state=new_state or goal_lifecycle_snapshot(goal),
        reason=(reason or "")[:200] or None,
        actor=actor,
        source=source,
    )
    db.add(event)
    return event


def detect_goal_change_type(previous: dict, current: dict) -> str | None:
    changed = {key for key in TRACKED_FIELDS if previous.get(key) != current.get(key)}
    if not changed:
        return None
    if "status" in changed:
        return "status_changed"
    if changed & {"recurrence", "days_of_week", "preferred_time", "duration_minutes", "start_date", "deadline"}:
        return "schedule_changed"
    if "content" in changed:
        return "content_changed"
    if changed - {"current_value"}:
        return "goal_updated"
    return None


def complete_goal_if_target_reached(
    db,
    goal: Goal,
    *,
    source: str,
) -> bool:
    target = float(goal.target_value or 0)
    current = float(goal.current_value or 0)
    if target <= 0 or current < target or goal.status == GoalStatus.completed.value:
        return False
    previous = goal_lifecycle_snapshot(goal)
    goal.status = GoalStatus.completed.value
    goal.updated_at = datetime.now(timezone.utc)
    record_goal_lifecycle_event(
        db,
        goal,
        event_type="target_completed",
        previous_state=previous,
        reason="目标进度已达到设定值",
        actor="system",
        source=source,
    )
    return True
