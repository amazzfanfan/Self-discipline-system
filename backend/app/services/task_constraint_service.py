from __future__ import annotations

import re


LIST_FIELDS = (
    "available_items",
    "unavailable_items",
    "preferred_locations",
    "avoid_activities",
)


def normalize_task_constraints(value: dict | None) -> dict:
    source = value or {}
    normalized = {
        field: list(dict.fromkeys(
            str(item).strip()[:50]
            for item in source.get(field, [])
            if str(item).strip()
        ))[:30]
        for field in LIST_FIELDS
    }
    max_minutes = source.get("max_task_minutes")
    normalized["max_task_minutes"] = (
        max(5, min(240, int(max_minutes))) if max_minutes else None
    )
    normalized["notes"] = str(source.get("notes") or "").strip()[:500]
    return normalized


def merge_task_constraints(current: dict | None, updates: dict) -> dict:
    merged = normalize_task_constraints(current)
    for field in LIST_FIELDS:
        additions = [str(item).strip() for item in updates.get(field, []) if str(item).strip()]
        if additions:
            merged[field] = list(dict.fromkeys([*merged[field], *additions]))[:30]
    if "max_task_minutes" in updates and updates["max_task_minutes"] is not None:
        merged["max_task_minutes"] = max(5, min(240, int(updates["max_task_minutes"])))
    if updates.get("notes"):
        merged["notes"] = str(updates["notes"]).strip()[:500]
    # An explicit availability update overrides an older unavailable marker and vice versa.
    for item in merged["available_items"]:
        merged["unavailable_items"] = [old for old in merged["unavailable_items"] if old != item]
    unavailable_updates = {
        str(item).strip()
        for item in updates.get("unavailable_items", [])
        if str(item).strip()
    }
    for item in unavailable_updates:
        merged["available_items"] = [old for old in merged["available_items"] if old != item]
    return merged


def task_constraints_text(value: dict | None) -> str:
    constraints = normalize_task_constraints(value)
    parts = []
    labels = {
        "available_items": "可用物品/器材",
        "unavailable_items": "不可用物品/器材",
        "preferred_locations": "偏好场地",
        "avoid_activities": "避免活动",
    }
    for field, label in labels.items():
        if constraints[field]:
            parts.append(f"{label}：{'、'.join(constraints[field])}")
    if constraints["max_task_minutes"]:
        parts.append(f"单项任务最长：{constraints['max_task_minutes']}分钟")
    if constraints["notes"]:
        parts.append(f"补充说明：{constraints['notes']}")
    return "；".join(parts) if parts else "未提供特殊可执行条件"


def validate_task_feasibility(title: str, value: dict | None) -> tuple[bool, str | None]:
    constraints = normalize_task_constraints(value)
    compact_title = re.sub(r"\s+", "", title).lower()
    for item in [*constraints["unavailable_items"], *constraints["avoid_activities"]]:
        compact_item = re.sub(r"\s+", "", item).lower()
        if compact_item and compact_item in compact_title:
            return False, f"任务依赖用户标记为不可用的“{item}”"
    max_minutes = constraints["max_task_minutes"]
    durations = [int(item) for item in re.findall(r"(\d{1,3})\s*分钟", title)]
    if max_minutes and durations and max(durations) > max_minutes:
        return False, f"任务时长超过用户设置的 {max_minutes} 分钟上限"
    return True, None
