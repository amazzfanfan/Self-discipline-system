from app.models.task import Task, TaskEvent


def _value(value):
    return value.value if hasattr(value, "value") else value


async def record_task_event(
    db,
    task: Task,
    event_type: str,
    *,
    actor: str,
    source: str,
    reason: str | None = None,
    from_status=None,
    to_status=None,
    metadata: dict | None = None,
) -> TaskEvent:
    event = TaskEvent(
        task_id=task.id,
        user_id=task.user_id,
        event_type=event_type[:32],
        from_status=_value(from_status),
        to_status=_value(to_status),
        reason=(reason or "")[:200] or None,
        actor=actor[:20],
        source=source[:30],
        event_metadata=metadata or {},
    )
    db.add(event)
    return event
