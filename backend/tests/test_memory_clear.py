import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from app.modules.user.router import clear_my_memories


def test_clear_memories_invalidates_redis_and_resets_rolling_summary():
    user = SimpleNamespace(id=uuid.uuid4())
    result = MagicMock(rowcount=4)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    with (
        patch(
            "app.modules.user.router.reset_conversation_summary",
            new=AsyncMock(return_value=1),
        ) as reset,
        patch(
            "app.modules.user.router.invalidate_memory_search",
            new=AsyncMock(),
        ) as invalidate,
    ):
        response = asyncio.run(clear_my_memories(user=user, db=db))

    assert response == {"deleted": 4, "conversation_summaries_reset": 1}
    reset.assert_awaited_once_with(db, user.id)
    invalidate.assert_awaited_once_with(str(user.id))
