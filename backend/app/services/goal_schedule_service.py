from __future__ import annotations

import re
from datetime import date, time


WEEKDAY_NAMES = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


def parse_goal_schedule(content: str) -> dict:
    """Extract only high-confidence scheduling facts from a Chinese goal."""
    schedule: dict = {}
    if re.search(r"(?:每天|每日|每晚|每早)", content):
        schedule["recurrence"] = "daily"
    elif "工作日" in content:
        schedule["recurrence"] = "custom"
        schedule["days_of_week"] = [0, 1, 2, 3, 4]
    else:
        weekday_matches = re.findall(r"(?:周|星期)([一二三四五六日天])", content)
        if weekday_matches:
            schedule["recurrence"] = "weekly"
            schedule["days_of_week"] = sorted(
                {WEEKDAY_NAMES[item] for item in weekday_matches}
            )

    time_match = re.search(
        r"(凌晨|早上|上午|中午|下午|傍晚|晚上)?\s*(\d{1,2})\s*(?:点|时|[:：])\s*(\d{1,2})?\s*分?",
        content,
    )
    if time_match:
        period, hour_text, minute_text = time_match.groups()
        hour = int(hour_text)
        minute = int(minute_text or 0)
        if period in {"下午", "傍晚", "晚上"} and hour < 12:
            hour += 12
        elif period == "中午" and hour < 11:
            hour += 12
        elif period == "凌晨" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            schedule["preferred_time"] = time(hour, minute)

    duration_match = re.search(r"(?:持续|进行|运动|走|跑|练)?\s*(\d{1,3})\s*分钟", content)
    if duration_match:
        duration = int(duration_match.group(1))
        if 1 <= duration <= 600:
            schedule["duration_minutes"] = duration
    return schedule


def goal_is_due(goal: dict, target_date: date) -> bool:
    start_date = goal.get("start_date")
    deadline = goal.get("deadline")
    if start_date and date.fromisoformat(start_date) > target_date:
        return False
    if deadline and date.fromisoformat(deadline) < target_date:
        return False
    recurrence = goal.get("recurrence") or "flexible"
    if recurrence in {"flexible", "daily"}:
        return True
    return target_date.weekday() in set(goal.get("days_of_week") or [])


def goal_planning_context(goal: dict) -> str:
    parts = [goal["content"]]
    recurrence = goal.get("recurrence") or "flexible"
    if recurrence == "daily":
        parts.append("频率：每天")
    elif recurrence in {"weekly", "custom"} and goal.get("days_of_week"):
        names = "、".join("一二三四五六日"[day] for day in goal["days_of_week"])
        parts.append(f"执行日：周{names}")
    if goal.get("preferred_time"):
        parts.append(f"计划时间：{goal['preferred_time']}")
    if goal.get("duration_minutes"):
        parts.append(f"计划时长：{goal['duration_minutes']} 分钟")
    progress = goal.get("progress_summary") or {}
    if progress.get("scheduled_to_date"):
        parts.append(
            "本周截至今天："
            f"计划 {progress['scheduled_to_date']} 次，"
            f"已完成 {progress.get('completed', 0)} 次"
        )
    if goal.get("completed_sessions"):
        parts.append(f"累计完成：{goal['completed_sessions']} 次")
    if goal.get("target_value") is not None:
        parts.append(
            f"目标进度：{goal.get('current_value') or 0}/{goal['target_value']}"
        )
    return "；".join(parts)
