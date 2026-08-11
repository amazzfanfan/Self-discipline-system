import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.models.score import DimensionEnum
from app.services.score_service import record_negative, record_task_completion


def _db_with_score(score):
    result = MagicMock()
    result.scalar_one.return_value = score
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _score(*, streak_days=0, last_completed_date=None):
    return SimpleNamespace(
        streak_days=streak_days,
        last_completed_date=last_completed_date,
        total_positive_count=0,
        total_negative_count=0,
        last_score_change=None,
    )


def test_completion_streak_requires_consecutive_calendar_days():
    score = _score(streak_days=2, last_completed_date=date(2026, 8, 10))
    db = _db_with_score(score)

    result = asyncio.run(
        record_task_completion(
            db,
            "user-id",
            DimensionEnum.exercise,
            date(2026, 8, 11),
        )
    )

    assert result["streak"] == 3
    assert score.last_completed_date == date(2026, 8, 11)
    assert score.total_positive_count == 1


def test_completion_after_gap_restarts_and_same_day_is_idempotent():
    score = _score(streak_days=5, last_completed_date=date(2026, 8, 8))
    db = _db_with_score(score)

    asyncio.run(
        record_task_completion(
            db,
            "user-id",
            DimensionEnum.sleep,
            date(2026, 8, 11),
        )
    )
    asyncio.run(
        record_task_completion(
            db,
            "user-id",
            DimensionEnum.sleep,
            date(2026, 8, 11),
        )
    )

    assert score.streak_days == 1
    assert score.total_positive_count == 1


def test_expired_task_resets_streak():
    score = _score(streak_days=4, last_completed_date=date(2026, 8, 10))
    db = _db_with_score(score)

    asyncio.run(
        record_negative(
            db,
            "user-id",
            DimensionEnum.diet,
            "任务过期",
            date(2026, 8, 11),
        )
    )

    assert score.streak_days == 0
    assert score.total_negative_count == 1
