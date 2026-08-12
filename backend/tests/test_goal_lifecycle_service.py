import uuid
from unittest.mock import MagicMock

from app.models.goal import Goal, GoalLifecycleEvent
from app.services.goal_lifecycle_service import complete_goal_if_target_reached


def test_goal_is_auto_completed_when_target_is_reached():
    goal = Goal(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        content="完成三次训练",
        goal_type="exercise",
        status="active",
        target_value=3,
        current_value=3,
    )
    db = MagicMock()

    completed = complete_goal_if_target_reached(db, goal, source="test")

    assert completed is True
    assert goal.status == "completed"
    event = db.add.call_args.args[0]
    assert isinstance(event, GoalLifecycleEvent)
    assert event.event_type == "target_completed"
    assert event.previous_state["status"] == "active"
    assert event.new_state["status"] == "completed"


def test_goal_below_target_remains_active():
    goal = Goal(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        content="完成三次训练",
        goal_type="exercise",
        status="active",
        target_value=3,
        current_value=2,
    )
    db = MagicMock()

    assert complete_goal_if_target_reached(db, goal, source="test") is False
    assert goal.status == "active"
    db.add.assert_not_called()


def test_decrease_metric_completes_when_value_reaches_lower_target():
    goal = Goal(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        content="体重降到 70kg",
        goal_type="exercise",
        status="active",
        target_metric="体重",
        target_unit="kg",
        metric_direction="decrease",
        target_value=70,
        baseline_value=75,
        current_value=69.8,
        progress_mode="manual",
    )
    db = MagicMock()

    assert complete_goal_if_target_reached(db, goal, source="test") is True
    assert goal.status == "completed"
