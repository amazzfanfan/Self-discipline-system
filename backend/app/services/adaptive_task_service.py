from __future__ import annotations

from dataclasses import asdict, dataclass

from app.models.task import DifficultyEnum, TaskStatusEnum


ADAPTATION_VERSION = "adaptive-v2.1"


def _value(value):
    return value.value if hasattr(value, "value") else value


@dataclass(frozen=True)
class HistorySignals:
    history_count: int
    decided_count: int
    adherence: float
    total_adjustments: int
    adjustment_rate: float
    too_easy: int
    too_hard: int
    not_suitable: int
    recent_failures: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AdaptiveDecision:
    difficulty: DifficultyEnum
    estimated_minutes: str
    rationale: str
    metadata: dict


def analyze_history(tasks: list, events: list | None = None) -> HistorySignals:
    decided = [
        task
        for task in tasks
        if _value(getattr(task, "status", None)) in {
            TaskStatusEnum.completed.value,
            TaskStatusEnum.failed.value,
        }
    ]
    completed = sum(
        _value(getattr(task, "status", None)) == TaskStatusEnum.completed.value
        for task in decided
    )
    adherence = completed / len(decided) if decided else 0.6
    user_adjustment_types = {"snoozed", "rescheduled", "excused"}
    user_adjustments = [
        event
        for event in (events or [])
        if getattr(event, "event_type", None) in user_adjustment_types
        and getattr(event, "actor", None) in {"user", "agent"}
    ]
    observed_task_ids = {
        getattr(event, "task_id", None)
        for event in (events or [])
        if getattr(event, "event_type", None) != "legacy_snapshot"
    }
    legacy_adjusted_tasks = [
        task
        for task in tasks
        if getattr(task, "id", None) not in observed_task_ids
        and (
            _value(getattr(task, "disposition", None)) in {"excused", "rescheduled"}
            or (getattr(task, "defer_count", 0) or 0) > 0
        )
    ]
    adjusted_task_ids = {
        getattr(event, "task_id", None) for event in user_adjustments
    } | {getattr(task, "id", id(task)) for task in legacy_adjusted_tasks}
    total_adjustments = len(user_adjustments) + sum(
        getattr(task, "defer_count", 0) or 0 for task in legacy_adjusted_tasks
    )
    feedback = [getattr(task, "user_feedback", None) for task in tasks]
    recent_decided = decided[:3]
    return HistorySignals(
        history_count=len(tasks),
        decided_count=len(decided),
        adherence=round(adherence, 3),
        total_adjustments=total_adjustments,
        adjustment_rate=round(len(adjusted_task_ids) / len(tasks), 3) if tasks else 0.0,
        too_easy=feedback.count("too_easy"),
        too_hard=feedback.count("too_hard"),
        not_suitable=feedback.count("not_suitable"),
        recent_failures=sum(
            _value(getattr(task, "status", None)) == TaskStatusEnum.failed.value
            for task in recent_decided
        ),
    )


def choose_task_budget(configured_budget: int, checkin) -> int:
    configured = min(max(int(configured_budget), 1), 4)
    if checkin is None:
        return configured
    available = int(checkin.available_minutes)
    energy = int(checkin.energy)
    stress = int(checkin.stress)
    if available <= 15 or energy <= 1:
        return 1
    if available <= 35 or energy <= 2 or stress >= 5:
        return min(2, configured)
    if available <= 70 or stress >= 4:
        return min(3, configured)
    return configured


def dimension_priority(*, baseline: float, has_goal: bool, signals: HistorySignals) -> float:
    priority = (35.0 if has_goal else 0.0) + (100.0 - baseline) * 0.35
    if signals.decided_count:
        priority += (1.0 - signals.adherence) * 20.0
    priority += min(signals.adjustment_rate * 8.0, 8.0)
    return round(priority, 2)


def decide_adaptation(
    *,
    baseline: float,
    signals: HistorySignals,
    checkin,
    task_budget: int,
) -> AdaptiveDecision:
    available = int(checkin.available_minutes) if checkin else 90
    energy = int(checkin.energy) if checkin else 3
    stress = int(checkin.stress) if checkin else 3
    minutes_per_task = max(5, available // max(task_budget, 1))
    pressure = 0
    growth = 0
    reasons: list[str] = []

    if energy <= 2:
        pressure += 2
        reasons.append("今日精力偏低")
    if stress >= 4:
        pressure += 1
        reasons.append("今日压力偏高")
    if minutes_per_task < 20:
        pressure += 2
        reasons.append("单项可用时间有限")
    if signals.decided_count >= 3 and signals.adherence < 0.5:
        pressure += 2
        reasons.append("近期完成率低于 50%")
    elif signals.decided_count >= 3 and signals.adherence < 0.7:
        pressure += 1
        reasons.append("近期完成率仍需稳定")
    if (
        signals.total_adjustments >= 3
        or (signals.history_count >= 3 and signals.adjustment_rate >= 0.4)
    ):
        pressure += 2
        reasons.append("近期任务调整较频繁")
    if signals.too_hard >= 2:
        pressure += 2
        reasons.append("多次反馈任务太难")
    if signals.not_suitable >= 2:
        pressure += 1
        reasons.append("多次反馈任务不适合")

    if signals.decided_count >= 4 and signals.adherence >= 0.85:
        growth += 2
        reasons.append("近期完成率稳定在 85% 以上")
    if signals.too_easy >= 2:
        growth += 2
        reasons.append("多次反馈任务太简单")
    if energy >= 4 and stress <= 3 and minutes_per_task >= 35:
        growth += 1
        reasons.append("今日状态与时间充足")
    if baseline >= 70:
        growth += 1

    if pressure >= 2:
        difficulty = DifficultyEnum.easy
    elif growth >= 4 and pressure == 0:
        difficulty = DifficultyEnum.hard
    else:
        difficulty = DifficultyEnum.medium

    if minutes_per_task <= 10:
        estimated = "5-10"
    elif minutes_per_task < 20 or difficulty == DifficultyEnum.easy:
        estimated = "10-20"
    elif minutes_per_task < 35 or difficulty == DifficultyEnum.medium:
        estimated = "20-30"
    else:
        estimated = "35-50"

    if reasons:
        rationale = "；".join(reasons[:3]) + "，因此调整任务强度与时长"
    else:
        rationale = "近期行为数据较少，采用中等强度并继续观察反馈"
    metadata = {
        "version": ADAPTATION_VERSION,
        "difficulty": difficulty.value,
        "estimated_minutes": estimated,
        "pressure_score": pressure,
        "growth_score": growth,
        "minutes_per_task": minutes_per_task,
        "signals": signals.to_dict(),
        "reasons": reasons[:5],
    }
    return AdaptiveDecision(difficulty, estimated, rationale, metadata)
