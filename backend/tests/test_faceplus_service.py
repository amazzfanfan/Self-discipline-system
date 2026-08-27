import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import faceplus_service


def complete_faceplus_result() -> dict:
    return {
        "skin_type": {"skin_type": 2},
        **{
            field: {"value": 0}
            for field in faceplus_service.SCORED_SIGNAL_FIELDS
        },
    }


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


def test_faceplus_score_requires_all_provider_fields():
    complete = faceplus_service._faceplus_field_coverage(
        complete_faceplus_result()
    )
    incomplete_result = complete_faceplus_result()
    incomplete_result.pop("skin_spot")
    incomplete = faceplus_service._faceplus_field_coverage(incomplete_result)

    assert complete == {
        "present": 15,
        "expected": 15,
        "complete": True,
        "missing": [],
    }
    assert incomplete["complete"] is False
    assert incomplete["missing"] == ["skin_spot"]


def test_incomplete_faceplus_result_never_becomes_perfect_score():
    raw = complete_faceplus_result()
    raw.pop("dark_circle")
    coverage = faceplus_service._faceplus_field_coverage(raw)

    result = faceplus_service._get_incomplete_result(raw, "a" * 64, coverage)

    assert result.source == "faceplusplus_incomplete"
    assert result.skin_score is None
    assert result.field_coverage == coverage
    assert "字段不完整" in result.error


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
    assert kwargs["temperature"] == 0
    assert kwargs["max_tokens"] == faceplus_service.SKIN_SUGGESTION_MAX_TOKENS
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


def test_safe_skin_suggestions_skip_model_when_no_issues(monkeypatch):
    completion = AsyncMock()
    monkeypatch.setattr(faceplus_service, "chat_completion_with_fallback", completion)

    suggestions, error = asyncio.run(
        faceplus_service.generate_ai_suggestions_safely([], "中性")
    )

    assert suggestions == []
    assert error is None
    completion.assert_not_awaited()


def test_safe_skin_suggestions_preserve_analysis_on_invalid_json(monkeypatch):
    monkeypatch.setattr(
        faceplus_service,
        "chat_completion_with_fallback",
        AsyncMock(return_value='{"suggestions":["内容未结束"'),
    )
    monkeypatch.setattr(
        faceplus_service,
        "increment_metric",
        AsyncMock(),
    )

    suggestions, error = asyncio.run(
        faceplus_service.generate_ai_suggestions_safely(["眼袋"], "中性")
    )

    assert suggestions == []
    assert "建议暂时不可用" in error


def test_skin_suggestions_retry_once_after_truncated_json(monkeypatch):
    completion = AsyncMock(
        side_effect=[
            '{"suggestions":[{"text":"内容未结束',
            '{"suggestions":[{"text":"晚间温和清洁并使用清爽保湿乳",'
            '"risk_level":"low","cautions":["先局部试用"]}]}',
        ]
    )
    monkeypatch.setattr(faceplus_service, "chat_completion_with_fallback", completion)
    retry_metric = AsyncMock()
    monkeypatch.setattr(faceplus_service, "increment_metric", retry_metric)

    suggestions = asyncio.run(
        faceplus_service.generate_ai_suggestions(["左脸颊毛孔粗大"], "中性")
    )

    assert suggestions == ["晚间温和清洁并使用清爽保湿乳（注意：先局部试用）"]
    assert completion.await_count == 2
    first_call, retry_call = completion.await_args_list
    assert first_call.kwargs["max_tokens"] == faceplus_service.SKIN_SUGGESTION_MAX_TOKENS
    assert retry_call.kwargs["max_tokens"] == faceplus_service.SKIN_SUGGESTION_RETRY_MAX_TOKENS
    retry_metric.assert_awaited_once_with("ai:skin_suggestions:json_retry")


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
