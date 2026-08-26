from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import local_today
from app.models.goal import Goal, GoalStatus
from app.models.user import UserProfile
from app.models.weight import WeightRecord
from app.services.goal_lifecycle_service import (
    complete_goal_if_target_reached,
    goal_lifecycle_snapshot,
    goal_target_reached,
    record_goal_lifecycle_event,
)
from app.services.goal_progress_service import (
    record_manual_goal_progress,
    update_completed_milestones,
)


def is_body_weight_goal(goal: Goal) -> bool:
    """Match absolute body-weight goals without treating 'lose 5 kg' as 5 kg body weight."""
    unit = str(goal.target_unit or "").strip().lower()
    metric = str(goal.target_metric or "").strip().lower()
    content = str(goal.content or "").strip()
    structured = goal.structured_data if isinstance(goal.structured_data, dict) else {}
    explicit_kind = structured.get("metric_kind") == "body_weight"
    absolute_wording = bool(
        re.search(r"(?:体重|减重|增重).{0,10}(?:到|至|保持在)|目标体重", content)
    )
    return unit in {"kg", "公斤", "千克"} and (
        explicit_kind or metric in {"体重", "当前体重", "body weight", "weight"} or absolute_wording
    )


async def _sync_weight_goals(
    db: AsyncSession,
    user_id: str,
    weight_kg: float,
) -> list[dict]:
    goals = (
        await db.execute(
            select(Goal)
            .where(
                Goal.user_id == user_id,
                Goal.status.in_([GoalStatus.active.value, GoalStatus.completed.value]),
            )
            .with_for_update()
        )
    ).scalars().all()
    updated: list[dict] = []
    for goal in goals:
        if not is_body_weight_goal(goal):
            continue
        previous_state = goal_lifecycle_snapshot(goal)
        previous = float(goal.current_value) if goal.current_value is not None else weight_kg
        if goal.baseline_value is None:
            goal.baseline_value = previous
        goal.current_value = weight_kg
        event = await record_manual_goal_progress(
            db,
            goal,
            previous_value=previous,
            current_value=weight_kg,
            source="weight_record",
            note="由体重记录自动同步",
        )
        milestones = update_completed_milestones(goal)
        completed = complete_goal_if_target_reached(db, goal, source="weight_record")
        reopened = False
        if goal.status == GoalStatus.completed.value and not goal_target_reached(goal):
            goal.status = GoalStatus.active.value
            reopened = True
            record_goal_lifecycle_event(
                db,
                goal,
                event_type="completion_reverted",
                previous_state=previous_state,
                reason="最新体重不再满足目标值",
                actor="system",
                source="weight_record",
            )
        if event is not None or completed or reopened:
            updated.append(
                {
                    "id": str(goal.id),
                    "content": goal.content,
                    "previous_value": previous,
                    "current_value": weight_kg,
                    "completed": completed,
                    "reopened": reopened,
                    "completed_milestones": [item["id"] for item in milestones],
                }
            )
    return updated


def _moving_average(records: list[WeightRecord], days: int) -> float | None:
    cutoff = local_today() - timedelta(days=days - 1)
    values = [float(item.weight_kg) for item in records if item.recorded_at >= cutoff]
    return round(sum(values) / len(values), 2) if values else None


async def get_weight_history_payload(
    db: AsyncSession,
    user_id: str,
    *,
    limit: int = 90,
) -> dict:
    records = (
        await db.execute(
            select(WeightRecord)
            .where(WeightRecord.user_id == user_id)
            .order_by(WeightRecord.recorded_at.desc(), WeightRecord.created_at.desc())
            .limit(max(1, min(limit, 365)))
        )
    ).scalars().all()
    latest = float(records[0].weight_kg) if records else None

    def change_since(days: int) -> float | None:
        if latest is None:
            return None
        target = local_today() - timedelta(days=days)
        baseline = next((item for item in records if item.recorded_at <= target), None)
        return round(latest - float(baseline.weight_kg), 2) if baseline else None

    return {
        "records": [
            {
                "id": str(item.id),
                "weight_kg": float(item.weight_kg),
                "recorded_at": item.recorded_at.isoformat(),
                "source": item.source or "manual",
            }
            for item in reversed(records)
        ],
        "summary": {
            "latest_kg": latest,
            "change_7d": change_since(7),
            "change_30d": change_since(30),
            "average_7d": _moving_average(records, 7),
            "average_30d": _moving_average(records, 30),
            "sample_count": len(records),
        },
    }


async def record_weight(
    db: AsyncSession,
    user_id: str,
    weight_kg: float,
    *,
    source: str = "manual",
    recorded_at: date | None = None,
) -> dict:
    """Upsert a daily measurement, sync the profile snapshot and body-weight goals."""
    value = round(float(weight_kg), 1)
    if not 20 < value < 300:
        raise ValueError("体重必须在 20kg 到 300kg 之间")
    target_date = recorded_at or local_today()
    existing = await db.scalar(
        select(WeightRecord)
        .where(WeightRecord.user_id == user_id, WeightRecord.recorded_at == target_date)
        .with_for_update()
    )
    previous_today = float(existing.weight_kg) if existing else None
    if existing:
        existing.weight_kg = value
        existing.source = source
    else:
        # The unique daily key plus PostgreSQL upsert closes the race between
        # simultaneous profile/API/Agent writes from multiple clients.
        await db.execute(
            pg_insert(WeightRecord)
            .values(
                user_id=user_id,
                weight_kg=value,
                recorded_at=target_date,
                source=source,
            )
            .on_conflict_do_update(
                constraint="uq_weight_records_user_date",
                set_={"weight_kg": value, "source": source},
            )
        )

    profile = await db.scalar(
        select(UserProfile).where(UserProfile.user_id == user_id).with_for_update()
    )
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    profile.weight_kg = value
    await db.flush()

    linked_goals = await _sync_weight_goals(db, user_id, value)
    history = await get_weight_history_payload(db, user_id, limit=90)
    return {
        "message": "今日体重已更新" if previous_today is not None else "体重已记录",
        "weight_kg": value,
        "recorded_at": target_date.isoformat(),
        "updated_existing": previous_today is not None,
        "previous_today_kg": previous_today,
        "summary": history["summary"],
        "linked_goals": linked_goals,
    }
