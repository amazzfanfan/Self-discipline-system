from types import SimpleNamespace

from app.services.task_service import _resolve_task


def test_multiple_same_dimension_tasks_require_specific_keyword():
    tasks = [
        SimpleNamespace(title="跑步机爬坡走 40 分钟"),
        SimpleNamespace(title="完成 20 分钟力量训练"),
    ]

    task, error = _resolve_task(tasks, None, "没有任务")

    assert task is None
    assert error["requires_clarification"] is True
    assert error["candidates"] == [task.title for task in tasks]


def test_keyword_selects_one_task_without_guessing():
    tasks = [
        SimpleNamespace(title="跑步机爬坡走 40 分钟"),
        SimpleNamespace(title="完成 20 分钟力量训练"),
    ]

    task, error = _resolve_task(tasks, "爬坡", "没有任务")

    assert error is None
    assert task.title == "跑步机爬坡走 40 分钟"
