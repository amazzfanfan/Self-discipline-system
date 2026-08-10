import asyncio

import pytest

from app.services.ai_service import evaluate_all_scores
from app.services.assessment_service import RUBRIC_VERSION, evaluate_profile


ANSWERS = {
    "exercise_days": "3_4",
    "exercise_duration": "40_60",
    "sedentary_hours": "4_6",
    "meal_regularity": "usually",
    "vegetable_frequency": "two_plus",
    "sugary_drinks": "rarely",
    "sleep_duration": "7_9",
    "sleep_regularity": "regular",
    "sleep_quality": "good",
    "skincare_frequency": "daily",
    "sunscreen_frequency": "daily",
    "grooming_frequency": "daily",
}


def evaluate(**overrides):
    payload = {
        "height_cm": 175,
        "weight_kg": 70,
        "age": 25,
        "gender": "male",
        "questionnaire": ANSWERS,
        "photo_hash": "a" * 64,
    }
    payload.update(overrides)
    return evaluate_profile(**payload)


def test_structured_assessment_is_deterministic_and_explainable():
    first = evaluate()
    second = evaluate()

    assert first == second
    assert first.rubric_version == RUBRIC_VERSION
    assert first.mode == "rules"
    assert first.scores == {
        "exercise": 79.5,
        "diet": 85.4,
        "sleep": 90.8,
        "appearance": 90.0,
    }
    assert first.overall_confidence == 1.0
    assert first.evidence["exercise"]["source"] == "structured_questionnaire"
    assert len(first.evidence["exercise"]["components"]) == 3


def test_photo_hash_does_not_change_behavior_scores():
    first = evaluate(photo_hash="a" * 64)
    second = evaluate(photo_hash="b" * 64)

    assert first.input_hash != second.input_hash
    assert first.scores == second.scores


def test_missing_questionnaire_is_not_disguised_as_default_score():
    with pytest.raises(ValueError, match="状态问卷"):
        evaluate(questionnaire=None)


def test_compatibility_entry_does_not_call_a_visual_model():
    scores, mode = asyncio.run(
        evaluate_all_scores(
            175,
            70,
            25,
            "male",
            portrait_photo_url="/uploads/example.jpg",
            questionnaire=ANSWERS,
        )
    )

    assert mode == "rules"
    assert scores["exercise"] == 79.5

