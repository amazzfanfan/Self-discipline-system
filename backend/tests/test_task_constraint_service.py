from app.services.task_constraint_service import (
    merge_task_constraints,
    normalize_task_constraints,
    sanitize_constraint_phrase,
    task_constraints_text,
    validate_task_feasibility,
)


def test_unavailable_item_and_avoided_activity_reject_tasks():
    constraints = {
        "unavailable_items": ["眼霜"],
        "avoid_activities": ["跳绳"],
    }

    assert validate_task_feasibility("涂眼霜并按摩两分钟", constraints)[0] is False
    assert validate_task_feasibility("完成10分钟跳绳", constraints)[0] is False
    assert validate_task_feasibility("清水洁面两分钟", constraints)[0] is True


def test_duration_limit_is_enforced_and_rendered():
    constraints = {"max_task_minutes": 20, "preferred_locations": ["家里"]}

    assert validate_task_feasibility("快走30分钟", constraints)[0] is False
    assert validate_task_feasibility("拉伸15分钟", constraints)[0] is True
    assert "最长：20分钟" in task_constraints_text(constraints)


def test_new_availability_overrides_old_unavailable_item():
    result = merge_task_constraints(
        {"unavailable_items": ["瑜伽垫"]},
        {"available_items": ["瑜伽垫"]},
    )

    assert result["available_items"] == ["瑜伽垫"]
    assert result["unavailable_items"] == []


def test_conversational_suffix_is_not_saved_as_part_of_resource():
    assert sanitize_constraint_phrase("眼霜怎么办") == "眼霜"
    assert sanitize_constraint_phrase("瑜伽垫可以吗") == "瑜伽垫"
    assert normalize_task_constraints({"unavailable_items": ["眼霜怎么办"]})[
        "unavailable_items"
    ] == ["眼霜"]
