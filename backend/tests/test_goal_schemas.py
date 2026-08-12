import pytest
from pydantic import ValidationError

from app.modules.goals.router import GoalCreateRequest, GoalProgressRequest, GoalUpdateRequest


def test_goal_create_rejects_unknown_dimension():
    with pytest.raises(ValidationError):
        GoalCreateRequest(content="每天散步", goal_type="unknown")


def test_goal_update_rejects_invalid_status_and_values():
    with pytest.raises(ValidationError):
        GoalUpdateRequest(status="deleted")
    with pytest.raises(ValidationError):
        GoalUpdateRequest(target_value=0)
    with pytest.raises(ValidationError):
        GoalUpdateRequest(current_value=-1)


def test_goal_update_preserves_explicit_null_for_clearable_fields():
    body = GoalUpdateRequest(target_metric=None, target_value=None, deadline=None)

    assert body.model_dump(exclude_unset=True) == {
        "target_metric": None,
        "target_value": None,
        "deadline": None,
    }


def test_goal_update_rejects_empty_content():
    with pytest.raises(ValidationError):
        GoalUpdateRequest(content="")


def test_goal_schedule_fields_are_validated():
    body = GoalCreateRequest(
        content="每天晚上八点快走",
        recurrence="daily",
        preferred_time="20:00",
        duration_minutes=40,
        reminder_enabled=True,
    )
    assert body.preferred_time.isoformat() == "20:00:00"
    with pytest.raises(ValidationError):
        GoalCreateRequest(content="周一快走", days_of_week=[7])
    with pytest.raises(ValidationError):
        GoalUpdateRequest(duration_minutes=0)
    with pytest.raises(ValidationError):
        GoalUpdateRequest(progress_mode="automatic")


def test_structured_goal_metric_and_progress_are_validated():
    body = GoalCreateRequest(
        content="累计跑步 100 公里",
        target_metric="累计里程",
        target_unit="km",
        metric_direction="increase",
        target_value=100,
        current_value=12,
        milestones=[{"title": "完成 20 公里", "target_value": 20}],
        progress_mode="manual",
    )
    assert body.milestones[0].target_value == 20
    assert GoalProgressRequest(delta=5).delta == 5
    with pytest.raises(ValidationError):
        GoalProgressRequest()
    with pytest.raises(ValidationError):
        GoalProgressRequest(current_value=10, delta=2)
