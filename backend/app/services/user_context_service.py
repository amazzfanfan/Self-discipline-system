"""Query-aware structured user context for Agent responses.

The snapshot is assembled from authoritative tables at request time. It is not a
second free-form persona and it deliberately exposes only sections relevant to
the current request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_today
from app.models.behavior import DailyCheckIn
from app.models.score import UserScore
from app.models.task import Task
from app.models.user import User, UserProfile
from app.services.behavior_service import calculate_behavior_metrics
from app.services.weight_service import get_weight_history_payload


CONTEXT_VERSION = "user-context-v1"
DIMENSION_KEYWORDS = {
    "exercise": ("运动", "跑步", "快走", "健身", "锻炼", "爬坡", "游泳", "瑜伽", "骑行"),
    "diet": ("饮食", "吃", "三餐", "蔬菜", "水果", "饮料", "热量", "体重", "减重", "减脂"),
    "sleep": ("睡眠", "睡觉", "早睡", "熬夜", "作息", "失眠", "困"),
    "appearance": ("形象", "护肤", "皮肤", "眼袋", "黑眼圈", "痘", "防晒", "洗面奶"),
}


@dataclass(frozen=True)
class ContextSelection:
    dimensions: tuple[str, ...]
    include_scores: bool
    include_behavior: bool
    include_today: bool
    include_constraints: bool
    include_skin: bool
    include_weight: bool

    def labels(self) -> list[str]:
        sections = ["identity"]
        if self.include_scores:
            sections.append("baselines")
        if self.include_behavior:
            sections.append("behavior")
        if self.include_today:
            sections.append("today")
        if self.include_constraints:
            sections.append("constraints")
        if self.include_skin:
            sections.append("skin")
        if self.include_weight:
            sections.append("weight")
        return sections


def select_context(query: str) -> ContextSelection:
    text = query.strip().lower()
    dimensions = tuple(
        dimension
        for dimension, keywords in DIMENSION_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    )
    task_or_plan = any(
        keyword in text
        for keyword in ("任务", "计划", "安排", "建议", "应该", "适合", "怎么做", "目标")
    )
    behavior = task_or_plan or any(
        keyword in text
        for keyword in ("最近", "趋势", "完成率", "表现", "为什么", "复盘", "坚持")
    )
    today = task_or_plan or any(keyword in text for keyword in ("今天", "今日", "今晚", "现在"))
    weight = any(keyword in text for keyword in ("体重", "减重", "增重", "公斤", "kg", "bmi"))
    skin = "appearance" in dimensions
    constraints = task_or_plan or any(
        keyword in text
        for keyword in ("没有", "不能", "不适合", "器材", "物品", "地点", "最多")
    )
    return ContextSelection(
        dimensions=dimensions,
        include_scores=bool(dimensions) or task_or_plan,
        include_behavior=behavior,
        include_today=today,
        include_constraints=constraints,
        include_skin=skin,
        include_weight=weight,
    )


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


async def build_user_context(
    db: AsyncSession,
    user: User,
    query: str,
) -> dict:
    selection = select_context(query)
    profile = getattr(user, "profile", None)
    if profile is None:
        profile = await db.scalar(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )

    identity: dict[str, Any] = {"nickname": user.nickname}
    if profile:
        identity.update(
            {
                "age": profile.age,
                "gender": _enum_value(profile.gender),
            }
        )
        if selection.include_weight or "exercise" in selection.dimensions:
            identity.update(
                {
                    "height_cm": float(profile.height_cm) if profile.height_cm is not None else None,
                    "current_weight_kg": float(profile.weight_kg) if profile.weight_kg is not None else None,
                }
            )

    payload: dict[str, Any] = {
        "version": CONTEXT_VERSION,
        "selected_sections": selection.labels(),
        "identity": identity,
    }

    if selection.include_scores:
        scores = (
            await db.execute(select(UserScore).where(UserScore.user_id == user.id))
        ).scalars().all()
        allowed = set(selection.dimensions)
        payload["baselines"] = {
            _enum_value(item.dimension): {
                "score": round(float(item.baseline_score), 1),
                "streak_days": int(item.streak_days or 0),
            }
            for item in scores
            if not allowed or _enum_value(item.dimension) in allowed
        }

    if selection.include_behavior:
        metrics = await calculate_behavior_metrics(db, user.id)
        if selection.dimensions:
            metrics = {
                **metrics,
                "dimensions": {
                    key: value
                    for key, value in (metrics.get("dimensions") or {}).items()
                    if key in selection.dimensions
                },
            }
        payload["behavior"] = metrics

    if selection.include_today:
        today = local_today()
        checkin = await db.scalar(
            select(DailyCheckIn).where(
                DailyCheckIn.user_id == user.id,
                DailyCheckIn.checkin_date == today,
            )
        )
        task_result = await db.execute(
            select(Task)
            .where(Task.user_id == user.id, Task.scheduled_date == today)
            .order_by(Task.created_at)
        )
        tasks = task_result.scalars().all()
        allowed = set(selection.dimensions)
        payload["today"] = {
            "date": today.isoformat(),
            "checkin": (
                {
                    "energy": checkin.energy,
                    "mood": checkin.mood,
                    "stress": checkin.stress,
                    "available_minutes": checkin.available_minutes,
                    "sleep_hours": float(checkin.sleep_hours) if checkin.sleep_hours is not None else None,
                }
                if checkin
                else None
            ),
            "tasks": [
                {
                    "dimension": _enum_value(item.dimension),
                    "title": item.title,
                    "status": _enum_value(item.status),
                    "disposition": item.disposition,
                    "difficulty": _enum_value(item.difficulty),
                    "estimated_minutes": item.estimated_minutes,
                }
                for item in tasks
                if not allowed or _enum_value(item.dimension) in allowed
            ][:6],
        }

    if selection.include_constraints and profile:
        payload["constraints"] = {
            "task": profile.task_constraints or {},
            "skincare": profile.skincare_constraints or {} if selection.include_skin else {},
        }

    if selection.include_skin and profile:
        skin = profile.skin_analysis if isinstance(profile.skin_analysis, dict) else {}
        payload["skin"] = {
            key: skin.get(key)
            for key in ("source", "skin_type", "score", "issues")
            if skin.get(key) is not None
        }

    if selection.include_weight:
        payload["weight"] = (
            await get_weight_history_payload(db, str(user.id), limit=90)
        )["summary"]

    return payload
