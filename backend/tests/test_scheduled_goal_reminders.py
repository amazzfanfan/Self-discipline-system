import asyncio
from datetime import datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.core.time import app_timezone
from app.models.task import TaskStatusEnum
from app.services import scheduler_service


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_):
        return None


def test_scheduled_goal_reminder_is_sent_once_in_window(monkeypatch):
    now = datetime(2026, 8, 12, 19, 31, tzinfo=app_timezone())
    task = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        title="跑步机爬坡走 40 分钟",
        scheduled_time=time(20, 0),
        status=TaskStatusEnum.pending,
    )
    goal = SimpleNamespace(
        id=uuid4(),
        reminder_minutes_before=30,
    )
    result = MagicMock()
    result.all.return_value = [(task, goal)]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    notifier = AsyncMock()
    monkeypatch.setattr(scheduler_service, "local_now", lambda: now)
    monkeypatch.setattr(
        scheduler_service,
        "async_session",
        lambda: _SessionContext(session),
    )
    monkeypatch.setattr(scheduler_service, "create_notification", notifier)

    asyncio.run(scheduler_service.scheduled_goal_reminders())

    notifier.assert_awaited_once()
    assert notifier.await_args.kwargs["payload"]["scheduled_time"] == "20:00"
    session.commit.assert_awaited_once()
