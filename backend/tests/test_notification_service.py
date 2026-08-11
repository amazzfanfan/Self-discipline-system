import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.notification_service import create_notification


def _scalar(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def test_notification_is_persistent_and_deduplicated():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_scalar({"task_reminders": True}), _scalar(None)])

    item = asyncio.run(
        create_notification(
            db,
            user_id="user-id",
            kind="task_reminder",
            title="任务提醒时间到了",
            message="睡前阅读",
            dedupe_key="task-wakeup:1:1",
            setting_key="task_reminders",
        )
    )

    assert item is not None
    assert item.dedupe_key == "task-wakeup:1:1"
    db.add.assert_called_once_with(item)


def test_disabled_notification_setting_is_respected():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalar({"daily_tasks": False}))

    item = asyncio.run(
        create_notification(
            db,
            user_id="user-id",
            kind="daily_tasks",
            title="今日任务",
            message="有 3 项待办",
            dedupe_key="daily:2026-08-12",
            setting_key="daily_tasks",
        )
    )

    assert item is None
    db.add.assert_not_called()

