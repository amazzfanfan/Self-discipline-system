from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.score import DimensionEnum
from app.models.task import DifficultyEnum, TaskStatusEnum
from app.modules.task.router import _task_payload


def test_task_payload_has_same_fields_for_today_and_history_views():
    completed_at = datetime(2026, 8, 11, 8, 30, tzinfo=timezone.utc)
    task = SimpleNamespace(
        id=uuid4(),
        dimension=DimensionEnum.exercise,
        title="爬坡走 40 分钟",
        description="保持中等强度",
        difficulty=DifficultyEnum.medium,
        scheduled_date=date(2026, 8, 11),
        status=TaskStatusEnum.completed,
        completed_at=completed_at,
        rationale="结合长期目标生成",
        estimated_minutes="30-40",
        user_feedback="just_right",
    )

    payload = _task_payload(task)

    assert payload["difficulty"] == "medium"
    assert payload["description"] == "保持中等强度"
    assert payload["scheduled_date"] == "2026-08-11"
    assert payload["completed_at"] == completed_at.isoformat()
    assert payload["user_feedback"] == "just_right"
    assert payload["disposition"] is None
    assert payload["deferred_until"] is None
    assert payload["defer_count"] == 0
