from types import SimpleNamespace

from app.models.score import DimensionEnum
from app.services.adaptive_task_service import analyze_history
from app.services.scheduler_service import select_daily_planning_slots


def _inputs():
    scores = {
        dimension: SimpleNamespace(baseline_score=50)
        for dimension in DimensionEnum
    }
    signals = {dimension: analyze_history([], []) for dimension in DimensionEnum}
    return scores, signals


def test_multiple_due_goals_in_one_dimension_get_separate_slots():
    scores, signals = _inputs()
    goals = [
        {
            "id": "older-exercise",
            "goal_type": "exercise",
            "created_at": "2026-08-01T00:00:00+00:00",
            "last_progress_at": None,
        },
        {
            "id": "newer-exercise",
            "goal_type": "exercise",
            "created_at": "2026-08-02T00:00:00+00:00",
            "last_progress_at": None,
        },
    ]

    slots = select_daily_planning_slots(goals, scores, signals, task_budget=3)

    assert [goal["id"] for dim, goal in slots if goal] == [
        "older-exercise",
        "newer-exercise",
    ]
    assert len(slots) == 3


def test_least_recently_progressed_goal_wins_when_capacity_is_limited():
    scores, signals = _inputs()
    goals = [
        {
            "id": "recent",
            "goal_type": "exercise",
            "created_at": "2026-08-01T00:00:00+00:00",
            "last_progress_at": "2026-08-11T00:00:00+00:00",
        },
        {
            "id": "waiting",
            "goal_type": "exercise",
            "created_at": "2026-08-01T00:00:00+00:00",
            "last_progress_at": "2026-08-08T00:00:00+00:00",
        },
    ]

    slots = select_daily_planning_slots(goals, scores, signals, task_budget=1)

    assert slots[0][1]["id"] == "waiting"
