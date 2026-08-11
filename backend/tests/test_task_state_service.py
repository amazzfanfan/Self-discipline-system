import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.core.time import app_timezone
from app.models.task import TaskStatusEnum
from app.services import task_state_service


def _task(**overrides):
    values = {
        "id": "task-id",
        "user_id": "user-id",
        "dimension": "sleep",
        "title": "睡前阅读 15 分钟",
        "scheduled_date": date(2026, 8, 11),
        "status": TaskStatusEnum.pending,
        "disposition": None,
        "disposition_reason": None,
        "deferred_until": None,
        "defer_count": 0,
        "original_scheduled_date": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    result.scalars.return_value.first.return_value = items[0] if items else None
    return result


def test_later_snooze_wakes_automatically(monkeypatch):
    now = datetime(2026, 8, 11, 10, 0, tzinfo=app_timezone())
    monkeypatch.setattr(task_state_service, "local_now", lambda: now)
    monkeypatch.setattr(task_state_service, "local_today", lambda: now.date())
    notifier = AsyncMock()
    monkeypatch.setattr(task_state_service, "create_notification", notifier)
    task = _task()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([task]))

    result = asyncio.run(
        task_state_service.apply_task_schedule(
            db,
            task,
            mode="later",
            deferred_until=now + timedelta(hours=1),
        )
    )
    assert result["success"] is True
    assert task.status == TaskStatusEnum.deferred
    assert task.disposition == "snoozed"

    monkeypatch.setattr(task_state_service, "local_now", lambda: now + timedelta(hours=2))
    changed = asyncio.run(task_state_service.maintain_task_states(db, "user-id"))
    assert changed == {"user-id"}
    assert task.status == TaskStatusEnum.pending
    assert task.disposition is None
    notifier.assert_awaited_once()


def test_excused_task_is_not_reopened(monkeypatch):
    now = datetime(2026, 8, 11, 10, 0, tzinfo=app_timezone())
    monkeypatch.setattr(task_state_service, "local_now", lambda: now)
    monkeypatch.setattr(task_state_service, "local_today", lambda: now.date())
    task = _task()
    db = MagicMock()

    result = asyncio.run(
        task_state_service.apply_task_schedule(db, task, mode="excuse", reason="身体不适")
    )
    assert result["success"] is True
    assert task.status == TaskStatusEnum.deferred
    assert task.disposition == "excused"
    assert task.disposition_reason == "身体不适"


def test_overdue_pending_task_expires(monkeypatch):
    now = datetime(2026, 8, 11, 10, 0, tzinfo=app_timezone())
    monkeypatch.setattr(task_state_service, "local_now", lambda: now)
    task = _task(scheduled_date=date(2026, 8, 10))
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([task]))
    record_negative = AsyncMock()
    monkeypatch.setattr(task_state_service, "record_negative", record_negative)

    changed = asyncio.run(task_state_service.maintain_task_states(db, "user-id"))
    assert changed == {"user-id"}
    assert task.status == TaskStatusEnum.failed
    assert task.disposition == "expired"
    record_negative.assert_awaited_once()
