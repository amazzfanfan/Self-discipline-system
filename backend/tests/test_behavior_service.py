import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.core.time import local_today
from app.models.score import DimensionEnum
from app.models.task import TaskStatusEnum
from app.services.behavior_service import calculate_behavior_metrics, last_completed_week_start


def _result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def test_behavior_metrics_separate_baseline_from_adherence():
    tasks = [
        SimpleNamespace(
            scheduled_date=local_today(),
            dimension=DimensionEnum.exercise,
            status=TaskStatusEnum.completed,
        ),
        SimpleNamespace(
            scheduled_date=local_today(),
            dimension=DimensionEnum.exercise,
            status=TaskStatusEnum.failed,
        ),
        SimpleNamespace(
            scheduled_date=local_today(),
            dimension=DimensionEnum.diet,
            status=TaskStatusEnum.deferred,
        ),
    ]
    scores = [
        SimpleNamespace(dimension=DimensionEnum.exercise, baseline_score=80, streak_days=2),
        SimpleNamespace(dimension=DimensionEnum.diet, baseline_score=70, streak_days=0),
    ]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(tasks), _result(scores)])

    metrics = asyncio.run(calculate_behavior_metrics(db, "user-id"))

    exercise = metrics["dimensions"]["exercise"]
    assert exercise["baseline"] == 80
    assert exercise["adherence_7d"] == 50
    assert exercise["momentum"] == 50
    assert exercise["sample_count_7d"] == 2
    assert exercise["confidence"] == "low"
    assert metrics["dimensions"]["diet"]["adherence_7d"] is None
    assert metrics["dimensions"]["diet"]["momentum"] is None
    assert metrics["overall"]["momentum"] == 50


def test_last_completed_week_is_previous_monday():
    from datetime import date

    assert last_completed_week_start(date(2026, 8, 12)) == date(2026, 8, 3)
    assert last_completed_week_start(date(2026, 8, 17)) == date(2026, 8, 10)
