import pytest
from pydantic import ValidationError

from app.modules.goals.router import GoalCreateRequest, GoalUpdateRequest


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
