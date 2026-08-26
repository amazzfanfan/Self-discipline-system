import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.goal_service import goal_service
from app.services.memory_service import MemoryService


def run(coro):
    return asyncio.run(coro)


def test_goal_vector_search_builds_typed_pgvector_expression():
    goal = MagicMock()
    goal.to_dict.return_value = {"id": str(uuid.uuid4()), "content": "每天遛狗"}
    result = MagicMock()
    result.all.return_value = [(goal, 0.82)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    with patch(
        "app.services.goal_service.get_embedding",
        new=AsyncMock(return_value=[0.1] * 1536),
    ):
        goals = run(
            goal_service.search_goals(
                db,
                str(uuid.uuid4()),
                "我的狗叫可乐",
                top_k=3,
                status="active",
            )
        )

    assert goals[0]["similarity"] == 0.82
    db.execute.assert_awaited_once()


def test_memory_vector_search_builds_typed_pgvector_expression():
    now = datetime.now(timezone.utc)
    memory = SimpleNamespace(
        id=uuid.uuid4(),
        content="我养的一只狗叫可乐",
        role="user",
        memory_type="personal",
        importance_score=0.9,
        access_count=0,
        last_accessed=None,
        created_at=now,
    )
    result = MagicMock()
    result.all.return_value = [(memory, 0.88)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    service = MemoryService(db, llm_client=MagicMock())

    with (
        patch(
            "app.services.memory_service.get_cached_memory_search",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.memory_service.get_embedding",
            new=AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "app.services.memory_service.set_cached_memory_search",
            new=AsyncMock(),
        ),
    ):
        memories = run(
            service.search_similar_memories(
                str(uuid.uuid4()),
                "我的狗叫什么",
                top_k=3,
                min_importance=0.2,
            )
        )

    assert memories[0]["content"] == "我养的一只狗叫可乐"
    assert memories[0]["similarity"] == 0.88
    db.execute.assert_awaited_once()
