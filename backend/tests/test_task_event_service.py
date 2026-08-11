import asyncio
import uuid
from unittest.mock import MagicMock

from app.models.score import DimensionEnum
from app.models.task import Task, TaskStatusEnum
from app.services.task_event_service import record_task_event


def test_record_task_event_captures_transition_and_metadata():
    task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        dimension=DimensionEnum.sleep,
        title="睡前阅读",
        scheduled_date=None,
    )
    db = MagicMock()

    event = asyncio.run(
        record_task_event(
            db,
            task,
            "snoozed",
            actor="user",
            source="api",
            reason="稍后再做",
            from_status=TaskStatusEnum.pending,
            to_status=TaskStatusEnum.deferred,
            metadata={"minutes": 30},
        )
    )

    assert event.task_id == task.id
    assert event.from_status == "pending"
    assert event.to_status == "deferred"
    assert event.event_metadata == {"minutes": 30}
    db.add.assert_called_once_with(event)
