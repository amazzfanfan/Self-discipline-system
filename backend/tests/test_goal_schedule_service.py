from datetime import date, time

from app.services.goal_schedule_service import (
    goal_is_due,
    goal_planning_context,
    parse_goal_schedule,
)


def test_parse_daily_evening_goal_extracts_time_and_duration():
    schedule = parse_goal_schedule("每天晚上8点在跑步机上爬坡走40分钟")

    assert schedule == {
        "recurrence": "daily",
        "preferred_time": time(20, 0),
        "duration_minutes": 40,
    }


def test_weekday_goal_is_due_only_on_selected_days():
    goal = {
        "content": "工作日散步",
        "recurrence": "custom",
        "days_of_week": [0, 1, 2, 3, 4],
        "preferred_time": "18:30",
        "duration_minutes": 30,
        "start_date": None,
        "deadline": None,
    }

    assert goal_is_due(goal, date(2026, 8, 12)) is True
    assert goal_is_due(goal, date(2026, 8, 15)) is False
    assert "计划时间：18:30" in goal_planning_context(goal)
    assert "计划时长：30 分钟" in goal_planning_context(goal)
