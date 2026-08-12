from __future__ import annotations

import re
from typing import Any


MEDICAL_CLAIM_PATTERN = re.compile(
    r"(治疗|治愈|根治|药到病除|替代医生|无需就医|处方药|口服|注射|针刺)"
)
RETINOID_PATTERN = re.compile(r"(维\s*[Aa]|视黄醇|视黄醛|维甲酸|阿达帕林|他扎罗汀)", re.I)
STRONG_ACTIVE_PATTERN = re.compile(
    r"(高浓度.{0,6}(?:酸|酒精|维\s*[Cc])|刷酸|水杨酸|果酸|杏仁酸|壬二酸|过氧化苯甲酰|磨砂|去角质)"
)


def skincare_constraints_text(constraints: dict | None) -> str:
    constraints = constraints or {}
    items = []
    if constraints.get("sensitive_skin"):
        items.append("敏感肌：避免强刺激、高浓度活性成分和频繁去角质")
    if constraints.get("pregnancy_or_breastfeeding"):
        items.append("孕期或哺乳期：禁止推荐维A类、视黄醇和维甲酸类成分")
    if constraints.get("skin_barrier_damaged"):
        items.append("皮肤屏障受损：只建议温和清洁、保湿和防晒，不建议刷酸或磨砂")
    if constraints.get("prescription_treatment"):
        items.append("正在接受处方治疗：不得新增功效型活性成分，应先咨询开方医生")
    allergies = [str(item).strip() for item in constraints.get("allergies", []) if str(item).strip()]
    if allergies:
        items.append(f"已知过敏成分：{', '.join(allergies[:20])}，不得推荐")
    return "；".join(items) if items else "未提供特殊限制；仍应避免医疗诊断和绝对功效承诺"


def validate_skin_suggestions(
    raw_items: Any,
    constraints: dict | None = None,
    *,
    limit: int = 3,
) -> list[str]:
    """Keep AI-authored advice only when it passes deterministic safety checks."""
    if not isinstance(raw_items, list):
        raise RuntimeError("AI skin suggestion response has no suggestions array")
    constraints = constraints or {}
    allergies = [
        str(item).strip().lower()
        for item in constraints.get("allergies", [])
        if str(item).strip()
    ]
    safe: list[str] = []
    rejected: list[str] = []

    for item in raw_items:
        if isinstance(item, dict):
            advice = str(item.get("text") or item.get("suggestion") or "").strip()
            cautions = item.get("cautions") or []
        else:
            advice = str(item).strip()
            cautions = []
        if not advice or len(advice) > 220:
            rejected.append("invalid_length")
            continue
        lowered = advice.lower()
        if MEDICAL_CLAIM_PATTERN.search(advice):
            rejected.append("medical_claim")
            continue
        if any(allergen in lowered for allergen in allergies):
            rejected.append("known_allergen")
            continue
        if constraints.get("pregnancy_or_breastfeeding") and RETINOID_PATTERN.search(advice):
            rejected.append("pregnancy_retinoid")
            continue
        if (
            constraints.get("sensitive_skin")
            or constraints.get("skin_barrier_damaged")
            or constraints.get("prescription_treatment")
        ) and (STRONG_ACTIVE_PATTERN.search(advice) or RETINOID_PATTERN.search(advice)):
            rejected.append("restricted_active")
            continue

        clean_cautions = [str(value).strip() for value in cautions if str(value).strip()]
        if (
            constraints.get("sensitive_skin")
            and re.search(r"(精华|酸|维\s*[Cc]|烟酰胺|美白|祛痘)", advice, re.I)
            and not any("局部" in value or "测试" in value for value in clean_cautions)
        ):
            clean_cautions.append("先小范围局部试用，出现刺痛或红肿立即停用")
        rendered = advice
        if clean_cautions:
            rendered += f"（注意：{'；'.join(clean_cautions[:2])}）"
        safe.append(rendered)
        if len(safe) >= limit:
            break

    if not safe:
        reason = rejected[0] if rejected else "empty"
        raise RuntimeError(f"AI skin suggestions did not pass safety validation: {reason}")
    return safe
