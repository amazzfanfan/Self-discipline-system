from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services.goal_progress_service import expected_goal_occurrences


def _goal(**overrides):
    values = {
        "recurrence": "daily",
        "days_of_week": [],
        "start_date": None,
        "deadline": None,
        "created_at": datetime(2026, 8, 10, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_daily_expected_occurrences_are_bounded_by_creation_and_deadline():
    goal = _goal(deadline=date(2026, 8, 12))

    assert expected_goal_occurrences(
        goal,
        date(2026, 8, 3),
        date(2026, 8, 16),
    ) == 3


def test_weekly_expected_occurrences_only_count_selected_days():
    goal = _goal(
        recurrence="weekly",
        days_of_week=[0, 2, 4],
        created_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    assert expected_goal_occurrences(
        goal,
        date(2026, 8, 3),
        date(2026, 8, 9),
    ) == 3


def test_flexible_goal_has_no_synthetic_schedule():
    goal = _goal(recurrence="flexible")

    assert expected_goal_occurrences(
        goal,
        date(2026, 8, 10),
        date(2026, 8, 16),
    ) == 0


def test_paused_days_are_removed_from_expected_occurrences():
    goal = _goal(created_at=datetime(2026, 8, 10, tzinfo=timezone.utc))
    events = [
        SimpleNamespace(
            created_at=datetime(2026, 8, 11, 8, tzinfo=timezone.utc),
            new_state={"status": "paused"},
        ),
        SimpleNamespace(
            created_at=datetime(2026, 8, 13, 8, tzinfo=timezone.utc),
            new_state={"status": "active"},
        ),
    ]

    assert expected_goal_occurrences(
        goal,
        date(2026, 8, 10),
        date(2026, 8, 14),
        events,
    ) == 3


def test_completion_day_still_counts_as_an_expected_occurrence():
    goal = _goal(created_at=datetime(2026, 8, 10, tzinfo=timezone.utc))
    events = [
        SimpleNamespace(
            created_at=datetime(2026, 8, 12, 8, tzinfo=timezone.utc),
            new_state={"status": "completed"},
        )
    ]

    assert expected_goal_occurrences(
        goal,
        date(2026, 8, 10),
        date(2026, 8, 14),
        events,
    ) == 3
