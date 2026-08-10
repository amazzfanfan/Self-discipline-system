import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import ai_service


def test_task_generation_does_not_fall_back_to_a_template(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "chat_completion_with_fallback",
        AsyncMock(side_effect=TimeoutError("model timeout")),
    )

    with pytest.raises(TimeoutError, match="model timeout"):
        asyncio.run(
            ai_service.generate_task(
                nickname="测试用户",
                dimension="exercise",
                score=55,
                difficulty="medium",
                recent_tasks=[],
            )
        )


def test_task_generation_rejects_invalid_ai_content(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "chat_completion_with_fallback",
        AsyncMock(return_value='{"task":""}'),
    )

    with pytest.raises(RuntimeError, match="no valid task"):
        asyncio.run(
            ai_service.generate_task(
                nickname="测试用户",
                dimension="sleep",
                score=60,
                difficulty="medium",
                recent_tasks=[],
            )
        )
