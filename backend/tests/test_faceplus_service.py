import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import faceplus_service


def test_skin_score_uses_deterministic_penalties():
    raw_result = {
        "dark_circle": {"value": 1},
        "acne": {"value": 1},
        "pores_forehead": {"value": 1},
    }

    first = faceplus_service._calculate_skin_score(raw_result)
    second = faceplus_service._calculate_skin_score(raw_result)

    assert first == second
    assert first[0] == 79.0
    assert first[1] == ["黑眼圈", "痘痘", "额头毛孔粗大"]


def test_missing_faceplus_credentials_returns_unavailable(monkeypatch, tmp_path):
    async def cache_miss(*_args):
        return None

    monkeypatch.setattr(faceplus_service, "get_cached_skin_analysis", cache_miss)
    monkeypatch.setattr(faceplus_service.settings, "FACEPLUSPLUS_API_KEY", "")
    monkeypatch.setattr(faceplus_service.settings, "FACEPLUSPLUS_API_SECRET", "")
    image = tmp_path / "face.jpg"
    image.write_bytes(b"test-image")

    result = asyncio.run(faceplus_service.analyze_skin(str(image), "f" * 64))

    assert result.source == "unavailable"
    assert result.skin_score is None
    assert result.error


def test_skin_suggestions_are_ai_generated_without_thinking(monkeypatch):
    completion = AsyncMock(
        return_value='{"suggestions":["建议一","建议二"]}'
    )
    monkeypatch.setattr(faceplus_service, "chat_completion_with_fallback", completion)

    result = asyncio.run(
        faceplus_service.generate_ai_suggestions(["眼袋"], "中性")
    )

    assert result == ["建议一", "建议二"]
    kwargs = completion.await_args.kwargs
    assert kwargs["enable_thinking"] is False
    assert kwargs["num_retries"] == 0
    assert kwargs["timeout"] == 20


def test_skin_suggestions_do_not_fall_back_to_default(monkeypatch):
    monkeypatch.setattr(
        faceplus_service,
        "chat_completion_with_fallback",
        AsyncMock(side_effect=TimeoutError("model timeout")),
    )

    with pytest.raises(TimeoutError, match="model timeout"):
        asyncio.run(
            faceplus_service.generate_ai_suggestions(["眼袋"], "中性")
        )


def test_skin_suggestions_reject_pregnancy_retinoids(monkeypatch):
    monkeypatch.setattr(
        faceplus_service,
        "chat_completion_with_fallback",
        AsyncMock(
            return_value='{"suggestions": [{"text": "晚间使用视黄醇精华", "cautions": []}]}'
        ),
    )

    with pytest.raises(RuntimeError, match="pregnancy_retinoid"):
        asyncio.run(
            faceplus_service.generate_ai_suggestions(
                ["细纹"],
                "中性",
                {"pregnancy_or_breastfeeding": True},
            )
        )


def test_skin_suggestions_reject_known_allergen(monkeypatch):
    monkeypatch.setattr(
        faceplus_service,
        "chat_completion_with_fallback",
        AsyncMock(return_value='{"suggestions": ["使用烟酰胺精华改善暗沉"]}'),
    )

    with pytest.raises(RuntimeError, match="known_allergen"):
        asyncio.run(
            faceplus_service.generate_ai_suggestions(
                ["暗沉"],
                "中性",
                {"allergies": ["烟酰胺"]},
            )
        )


def test_sensitive_skin_suggestion_adds_patch_test(monkeypatch):
    monkeypatch.setattr(
        faceplus_service,
        "chat_completion_with_fallback",
        AsyncMock(return_value='{"suggestions": [{"text": "早间使用温和维C精华", "cautions": []}]}'),
    )

    result = asyncio.run(
        faceplus_service.generate_ai_suggestions(
            ["暗沉"],
            "中性",
            {"sensitive_skin": True},
        )
    )

    assert "局部试用" in result[0]


def test_skin_suggestions_reject_unavailable_product(monkeypatch):
    monkeypatch.setattr(
        faceplus_service,
        "chat_completion_with_fallback",
        AsyncMock(return_value='{"suggestions": ["晚间涂眼霜并按摩"]}'),
    )

    with pytest.raises(RuntimeError, match="unavailable user resources"):
        asyncio.run(
            faceplus_service.generate_ai_suggestions(
                ["眼袋"],
                "中性",
                None,
                {"unavailable_items": ["眼霜"]},
            )
        )
