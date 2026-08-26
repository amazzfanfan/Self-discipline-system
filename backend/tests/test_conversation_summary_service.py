import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from app.models.conversation import RoleEnum
from app.services.conversation_summary_service import (
    _clean_summary,
    empty_conversation_summary,
    refresh_conversation_summary,
)


def test_summary_schema_deduplicates_and_bounds_items():
    summary = _clean_summary(
        {
            "confirmed_facts": ["没有眼霜", "没有眼霜", "  "],
            "completed_actions": "invalid",
            "open_loops": ["等待确认替代任务"],
            "rejected_proposals": [],
            "narrative": "用户正在调整护理方案。",
        }
    )

    assert summary["confirmed_facts"] == ["没有眼霜"]
    assert summary["completed_actions"] == []
    assert summary["open_loops"] == ["等待确认替代任务"]


def test_empty_summary_has_explicit_open_loop_fields():
    summary = empty_conversation_summary()

    assert summary == {
        "confirmed_facts": [],
        "completed_actions": [],
        "open_loops": [],
        "rejected_proposals": [],
        "narrative": "",
    }


def test_refresh_summary_keeps_recent_six_messages_verbatim():
    user_id = uuid.uuid4()
    start = datetime(2026, 8, 24, tzinfo=timezone.utc)
    messages = [
        SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user_id,
            role=RoleEnum.user if index % 2 == 0 else RoleEnum.system,
            content=f"message-{index}",
            created_at=start + timedelta(minutes=index),
            extra_metadata={},
        )
        for index in range(12)
    ]
    profile = SimpleNamespace(memory_enabled=1)
    result = MagicMock()
    result.scalars.return_value.all.return_value = messages
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[profile, None])
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()

    with patch(
        "app.services.conversation_summary_service.chat_completion_with_fallback",
        new=AsyncMock(
            return_value=(
                '{"confirmed_facts":["用户没有眼霜"],"completed_actions":[],'
                '"open_loops":["等待确认替代任务"],"rejected_proposals":[],'
                '"narrative":"正在调整护理任务"}'
            )
        ),
    ) as llm:
        response = asyncio.run(refresh_conversation_summary(db, user_id))

    assert response["updated"] is True
    assert response["summarized"] == 6
    added = db.add.call_args.args[0]
    assert added.through_message_id == messages[5].id
    assert added.summary["open_loops"] == ["等待确认替代任务"]
    prompt_payload = llm.await_args.kwargs["messages"][1]["content"]
    assert "message-5" in prompt_payload
    assert "message-6" not in prompt_payload
