from types import SimpleNamespace

from app.models.task import DifficultyEnum, TaskStatusEnum
from app.services.adaptive_task_service import (
    analyze_history,
    choose_task_budget,
    decide_adaptation,
    dimension_priority,
)


def _task(status, feedback=None, defer_count=0, disposition=None):
    return SimpleNamespace(
        status=status,
        user_feedback=feedback,
        defer_count=defer_count,
        disposition=disposition,
    )


def test_low_energy_and_repeated_adjustments_reduce_difficulty():
    history = [
        _task(TaskStatusEnum.failed, "too_hard", 1, "rescheduled"),
        _task(TaskStatusEnum.failed, "too_hard", 1, "excused"),
        _task(TaskStatusEnum.completed, defer_count=1),
    ]
    signals = analyze_history(history)
    checkin = SimpleNamespace(available_minutes=25, energy=2, stress=4)

    decision = decide_adaptation(
        baseline=65,
        signals=signals,
        checkin=checkin,
        task_budget=2,
    )

    assert decision.difficulty == DifficultyEnum.easy
    assert decision.estimated_minutes in {"5-10", "10-20"}
    assert decision.metadata["pressure_score"] >= 2
    assert "近期任务调整较频繁" in decision.metadata["reasons"]


def test_high_adherence_and_too_easy_feedback_can_raise_difficulty():
    history = [
        _task(TaskStatusEnum.completed, "too_easy"),
        _task(TaskStatusEnum.completed, "too_easy"),
        _task(TaskStatusEnum.completed),
        _task(TaskStatusEnum.completed),
    ]
    signals = analyze_history(history)
    checkin = SimpleNamespace(available_minutes=120, energy=5, stress=2)

    decision = decide_adaptation(
        baseline=80,
        signals=signals,
        checkin=checkin,
        task_budget=2,
    )

    assert decision.difficulty == DifficultyEnum.hard
    assert decision.metadata["version"] == "adaptive-v2.1"
    assert "多次反馈任务太简单" in decision.metadata["reasons"]


def test_budget_and_dimension_priority_use_checkin_and_goals():
    checkin = SimpleNamespace(available_minutes=30, energy=2, stress=3)
    signals = analyze_history([])

    assert choose_task_budget(4, checkin) == 2
    assert dimension_priority(baseline=80, has_goal=True, signals=signals) > dimension_priority(
        baseline=80,
        has_goal=False,
        signals=signals,
    )
