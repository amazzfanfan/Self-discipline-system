from types import SimpleNamespace

from app.services.goal_progress_service import (
    normalize_goal_milestones,
    update_completed_milestones,
)


def test_milestones_are_stable_sorted_and_completed():
    milestones = normalize_goal_milestones(
        [
            {"title": "完成 10 公里", "target_value": 10},
            {"title": "完成 5 公里", "target_value": 5},
        ]
    )
    assert [item["target_value"] for item in milestones] == [5.0, 10.0]
    goal = SimpleNamespace(
        metric_direction="increase",
        current_value=6,
        milestones=milestones,
    )
    completed = update_completed_milestones(goal)
    assert [item["title"] for item in completed] == ["完成 5 公里"]
    assert goal.milestones[0]["completed_at"]


def test_decrease_milestones_complete_in_descending_order():
    milestones = normalize_goal_milestones(
        [
            {"title": "降到 72", "target_value": 72},
            {"title": "降到 70", "target_value": 70},
        ],
        direction="decrease",
    )
    goal = SimpleNamespace(
        metric_direction="decrease",
        current_value=71.5,
        milestones=milestones,
    )
    completed = update_completed_milestones(goal)
    assert [item["title"] for item in completed] == ["降到 72"]
