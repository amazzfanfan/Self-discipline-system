import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from app.services.weight_service import is_body_weight_goal, record_weight


def test_body_weight_goal_requires_absolute_weight_semantics():
    absolute = SimpleNamespace(
        target_unit="kg",
        target_metric="体重",
        content="将体重降到65kg",
        structured_data={"metric_kind": "body_weight"},
    )
    relative = SimpleNamespace(
        target_unit="kg",
        target_metric="减重总量",
        content="减重5kg",
        structured_data={},
    )

    assert is_body_weight_goal(absolute) is True
    assert is_body_weight_goal(relative) is False


def test_record_weight_updates_same_day_record_and_profile():
    user_id = str(uuid.uuid4())
    existing = SimpleNamespace(weight_kg=70.0, source="agent_chat")
    profile = SimpleNamespace(weight_kg=70.0)
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=[existing, profile])
    db.flush = AsyncMock()

    with (
        patch("app.services.weight_service._sync_weight_goals", new=AsyncMock(return_value=[])),
        patch(
            "app.services.weight_service.get_weight_history_payload",
            new=AsyncMock(
                return_value={
                    "records": [],
                    "summary": {"latest_kg": 69.2, "sample_count": 1},
                }
            ),
        ),
    ):
        result = asyncio.run(
            record_weight(
                db,
                user_id,
                69.2,
                source="profile_edit",
                recorded_at=date(2026, 8, 24),
            )
        )

    assert existing.weight_kg == 69.2
    assert existing.source == "profile_edit"
    assert profile.weight_kg == 69.2
    assert result["updated_existing"] is True
    assert result["previous_today_kg"] == 70.0


def test_record_weight_rejects_invalid_range():
    db = MagicMock()
    try:
        asyncio.run(record_weight(db, str(uuid.uuid4()), 500))
    except ValueError as exc:
        assert "20kg" in str(exc)
    else:
        raise AssertionError("invalid weight should fail")
