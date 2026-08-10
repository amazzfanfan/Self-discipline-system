"""Deterministic, explainable profile assessment.

The scoring contract is intentionally simple:
- questionnaire answers are converted to scores by versioned lookup tables;
- photos and generative models never decide exercise, diet, or sleep scores;
- the same normalized input and rubric version always produce the same result.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any


RUBRIC_VERSION = "profile-rules-v1"


@dataclass(frozen=True)
class AnswerOption:
    label: str
    score: float


@dataclass(frozen=True)
class QuestionRule:
    label: str
    weight: float
    options: dict[str, AnswerOption]


@dataclass(frozen=True)
class AssessmentResult:
    input_hash: str
    rubric_version: str
    mode: str
    scores: dict[str, float]
    evidence: dict[str, dict[str, Any]]
    confidence: dict[str, float]
    overall_confidence: float
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RUBRIC: dict[str, dict[str, QuestionRule]] = {
    "exercise": {
        "exercise_days": QuestionRule(
            label="每周主动运动天数",
            weight=0.4,
            options={
                "none": AnswerOption("几乎不运动", 20),
                "1_2": AnswerOption("每周 1–2 天", 50),
                "3_4": AnswerOption("每周 3–4 天", 80),
                "5_plus": AnswerOption("每周 5 天及以上", 92),
            },
        ),
        "exercise_duration": QuestionRule(
            label="单次运动时长",
            weight=0.35,
            options={
                "under_20": AnswerOption("少于 20 分钟", 35),
                "20_40": AnswerOption("20–40 分钟", 62),
                "40_60": AnswerOption("40–60 分钟", 82),
                "over_60": AnswerOption("60 分钟以上", 90),
            },
        ),
        "sedentary_hours": QuestionRule(
            label="每日久坐时长",
            weight=0.25,
            options={
                "under_4": AnswerOption("少于 4 小时", 90),
                "4_6": AnswerOption("4–6 小时", 75),
                "7_9": AnswerOption("7–9 小时", 50),
                "10_plus": AnswerOption("10 小时及以上", 25),
            },
        ),
    },
    "diet": {
        "meal_regularity": QuestionRule(
            label="三餐规律程度",
            weight=0.4,
            options={
                "rarely": AnswerOption("经常不规律", 30),
                "sometimes": AnswerOption("偶尔规律", 55),
                "usually": AnswerOption("大多数时候规律", 80),
                "always": AnswerOption("基本每天规律", 94),
            },
        ),
        "vegetable_frequency": QuestionRule(
            label="蔬果摄入频率",
            weight=0.3,
            options={
                "rarely": AnswerOption("很少", 25),
                "one": AnswerOption("每天约 1 次", 58),
                "two_plus": AnswerOption("每天 2 次及以上", 88),
            },
        ),
        "sugary_drinks": QuestionRule(
            label="含糖饮料频率",
            weight=0.3,
            options={
                "daily": AnswerOption("几乎每天", 25),
                "weekly": AnswerOption("每周 1–3 次", 60),
                "rarely": AnswerOption("很少或不喝", 90),
            },
        ),
    },
    "sleep": {
        "sleep_duration": QuestionRule(
            label="平均睡眠时长",
            weight=0.4,
            options={
                "under_6": AnswerOption("少于 6 小时", 25),
                "6_7": AnswerOption("6–7 小时", 58),
                "7_9": AnswerOption("7–9 小时", 92),
                "over_9": AnswerOption("9 小时以上", 68),
            },
        ),
        "sleep_regularity": QuestionRule(
            label="入睡和起床规律性",
            weight=0.3,
            options={
                "irregular": AnswerOption("经常变化", 30),
                "sometimes": AnswerOption("偶尔规律", 60),
                "regular": AnswerOption("基本固定", 90),
            },
        ),
        "sleep_quality": QuestionRule(
            label="醒后精神状态",
            weight=0.3,
            options={
                "poor": AnswerOption("经常疲惫", 30),
                "average": AnswerOption("一般", 60),
                "good": AnswerOption("大多数时候精神良好", 90),
            },
        ),
    },
    "appearance": {
        "skincare_frequency": QuestionRule(
            label="基础清洁和护肤频率",
            weight=0.4,
            options={
                "rarely": AnswerOption("很少", 30),
                "sometimes": AnswerOption("偶尔", 60),
                "daily": AnswerOption("基本每天", 90),
            },
        ),
        "sunscreen_frequency": QuestionRule(
            label="日间防晒习惯",
            weight=0.3,
            options={
                "rarely": AnswerOption("很少", 30),
                "sometimes": AnswerOption("按需使用", 65),
                "daily": AnswerOption("日间基本坚持", 90),
            },
        ),
        "grooming_frequency": QuestionRule(
            label="仪容整理习惯",
            weight=0.3,
            options={
                "rarely": AnswerOption("很少注意", 35),
                "sometimes": AnswerOption("重要场合会注意", 65),
                "daily": AnswerOption("日常保持整洁", 90),
            },
        ),
    },
}


def _normalized_payload(
    *,
    height_cm: float,
    weight_kg: float,
    age: int,
    gender: str,
    questionnaire: dict[str, str],
    photo_hash: str | None,
) -> dict[str, Any]:
    return {
        "rubric_version": RUBRIC_VERSION,
        "height_cm": round(float(height_cm), 1),
        "weight_kg": round(float(weight_kg), 1),
        "age": int(age),
        "gender": str(gender),
        "questionnaire": {
            str(key): str(value).strip().lower()
            for key, value in sorted(questionnaire.items())
        },
        "photo_hash": photo_hash or None,
    }


def build_assessment_input_hash(
    *,
    height_cm: float,
    weight_kg: float,
    age: int,
    gender: str,
    questionnaire: dict[str, str],
    photo_hash: str | None = None,
) -> str:
    payload = _normalized_payload(
        height_cm=height_cm,
        weight_kg=weight_kg,
        age=age,
        gender=gender,
        questionnaire=questionnaire,
        photo_hash=photo_hash,
    )
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _legacy_score(dimension: str, answer: str) -> float:
    """Best-effort deterministic compatibility for the former free-text form."""
    text = answer.strip().lower()
    if not text:
        return 50.0

    if dimension == "exercise":
        if any(word in text for word in ("不运动", "没有运动", "几乎不")):
            frequency = 20
        elif "每天" in text:
            frequency = 92
        else:
            match = re.search(r"(?:每周|一周)?\s*(\d+)\s*(?:次|天)", text)
            days = int(match.group(1)) if match else None
            frequency = 50 if days is None else 20 if days == 0 else 50 if days <= 2 else 80 if days <= 4 else 92
        duration_match = re.search(r"(\d+)\s*(?:分钟|分)", text)
        minutes = int(duration_match.group(1)) if duration_match else None
        duration = 50 if minutes is None else 35 if minutes < 20 else 62 if minutes < 40 else 82 if minutes <= 60 else 90
        return round((frequency + duration) / 2, 1)

    if dimension == "diet":
        positive = sum(word in text for word in ("规律", "蔬菜", "水果", "清淡", "健康"))
        negative = sum(word in text for word in ("不规律", "外卖", "甜", "饮料", "夜宵"))
        return float(max(20, min(90, 55 + positive * 10 - negative * 10)))

    if dimension == "sleep":
        duration_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|时)", text)
        hours = float(duration_match.group(1)) if duration_match else None
        score = 55 if hours is None else 25 if hours < 6 else 58 if hours < 7 else 92 if hours <= 9 else 68
        if any(word in text for word in ("规律", "精神", "睡得好")):
            score += 5
        if any(word in text for word in ("失眠", "熬夜", "疲惫")):
            score -= 15
        return float(max(20, min(95, score)))

    positive = sum(word in text for word in ("每天", "经常", "注意", "整洁", "护肤", "防晒"))
    negative = sum(word in text for word in ("不", "很少", "从不"))
    return float(max(25, min(90, 55 + positive * 8 - negative * 12)))


def evaluate_profile(
    *,
    height_cm: float,
    weight_kg: float,
    age: int,
    gender: str,
    questionnaire: dict[str, str] | None,
    photo_hash: str | None = None,
) -> AssessmentResult:
    if not questionnaire:
        raise ValueError("需要完成状态问卷后才能建立初始评分")

    scores: dict[str, float] = {}
    evidence: dict[str, dict[str, Any]] = {}
    confidence: dict[str, float] = {}
    warnings: list[str] = []
    structured_answers = sum(
        key in questionnaire
        for rules in RUBRIC.values()
        for key in rules
    )

    if structured_answers == 0:
        warnings.append("检测到旧版自由文本问卷，已使用确定性兼容规则；建议重新填写结构化问卷")
        for dimension in RUBRIC:
            raw_answer = questionnaire.get(dimension, "")
            scores[dimension] = _legacy_score(dimension, raw_answer)
            confidence[dimension] = 0.55 if raw_answer.strip() else 0.0
            evidence[dimension] = {
                "source": "legacy_questionnaire",
                "components": [
                    {
                        "label": "旧版问卷回答",
                        "answer": raw_answer or "未回答",
                        "score": scores[dimension],
                        "weight": 1.0,
                    }
                ],
            }
    else:
        for dimension, rules in RUBRIC.items():
            weighted_score = 0.0
            answered_weight = 0.0
            components: list[dict[str, Any]] = []
            for key, rule in rules.items():
                answer = str(questionnaire.get(key, "")).strip().lower()
                option = rule.options.get(answer)
                if option is None:
                    components.append(
                        {
                            "key": key,
                            "label": rule.label,
                            "answer": "未回答",
                            "score": None,
                            "weight": rule.weight,
                        }
                    )
                    continue
                weighted_score += option.score * rule.weight
                answered_weight += rule.weight
                components.append(
                    {
                        "key": key,
                        "label": rule.label,
                        "answer": option.label,
                        "score": option.score,
                        "weight": rule.weight,
                    }
                )

            # Missing answers stay neutral while lowering confidence. The new UI
            # requires every answer, but this keeps older API clients safe.
            missing_weight = max(0.0, 1.0 - answered_weight)
            scores[dimension] = round(weighted_score + 50.0 * missing_weight, 1)
            confidence[dimension] = round(answered_weight, 2)
            evidence[dimension] = {
                "source": "structured_questionnaire",
                "components": components,
            }
            if answered_weight < 1.0:
                warnings.append(f"{dimension} 维度存在未回答或无效选项")

    input_hash = build_assessment_input_hash(
        height_cm=height_cm,
        weight_kg=weight_kg,
        age=age,
        gender=gender,
        questionnaire=questionnaire,
        photo_hash=photo_hash,
    )
    overall_confidence = round(sum(confidence.values()) / len(confidence), 2)
    return AssessmentResult(
        input_hash=input_hash,
        rubric_version=RUBRIC_VERSION,
        mode="rules",
        scores=scores,
        evidence=evidence,
        confidence=confidence,
        overall_confidence=overall_confidence,
        warnings=list(dict.fromkeys(warnings)),
    )

