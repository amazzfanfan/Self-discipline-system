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

    with pytest.raises(RuntimeError, match="infeasible"):
        asyncio.run(
            ai_service.generate_task(
                nickname="测试用户",
                dimension="sleep",
                score=60,
                difficulty="medium",
                recent_tasks=[],
            )
        )


def test_task_generation_retries_when_candidate_uses_unavailable_item(monkeypatch):
    completion = AsyncMock(
        side_effect=[
            '{"task":"涂眼霜并按摩两分钟"}',
            '{"task":"清水洁面两分钟"}',
        ]
    )
    monkeypatch.setattr(ai_service, "chat_completion_with_fallback", completion)

    result = asyncio.run(
        ai_service.generate_task(
            nickname="测试用户",
            dimension="appearance",
            score=55,
            difficulty="easy",
            recent_tasks=[],
            task_constraints={"unavailable_items": ["眼霜"]},
        )
    )

    assert result == "清水洁面两分钟"
    assert completion.await_count == 2
