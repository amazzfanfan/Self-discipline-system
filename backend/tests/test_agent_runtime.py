import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.runtime import AgentRuntime
from app.agent.tools import ToolRegistry
from app.agent.types import PlannerDecision


def run(coro):
    return asyncio.run(coro)


def make_runtime() -> AgentRuntime:
    db = MagicMock()
    db.rollback = AsyncMock()
    return AgentRuntime(db, SimpleNamespace(id=uuid.uuid4(), nickname="Tester"))


def test_fallback_planner_records_explicit_weight():
    runtime = make_runtime()

    decision = runtime._fallback_decision("请记录一下，我今天体重 68.5 kg", [])

    assert decision.action == "tool"
    assert decision.tool == "record_weight"
    assert decision.arguments == {"weight_kg": 68.5}


def test_fallback_planner_marks_explicit_completed_task():
    runtime = make_runtime()

    decision = runtime._fallback_decision("今天的跑步任务已经完成了", [])

    assert decision.tool == "complete_task"
    assert decision.arguments == {"dimension": "exercise"}


def test_future_completion_intent_does_not_mark_task_complete():
    runtime = make_runtime()

    decision = runtime._fallback_decision("我想完成今天的跑步任务", [])

    assert decision.tool != "complete_task"


def test_explicit_goal_is_created_before_completion_keyword_is_considered():
    runtime = make_runtime()

    decision = runtime._fallback_decision("我的目标是每周完成三次跑步", [])

    assert decision.tool == "create_goal"
    assert decision.arguments["goal_type"] == "exercise"


def test_skip_tool_requires_explicit_confirmation():
    db = MagicMock()
    db.rollback = AsyncMock()
    registry = ToolRegistry(db, str(uuid.uuid4()))

    result, success, status, _ = run(
        registry.execute("skip_task", {"dimension": "sleep"}, "我不想做睡眠任务")
    )

    assert success is False
    assert status == "approval_required"
    assert result["requires_confirmation"] is True


def test_complete_tool_rejects_future_intent_even_if_planner_selects_it():
    db = MagicMock()
    db.rollback = AsyncMock()
    registry = ToolRegistry(db, str(uuid.uuid4()))

    result, success, status, _ = run(
        registry.execute(
            "complete_task", {"dimension": "exercise"}, "我想完成今天的跑步任务"
        )
    )

    assert success is False
    assert status == "approval_required"
    assert result["requires_confirmation"] is True


def test_tool_arguments_are_schema_validated_before_execution():
    db = MagicMock()
    db.rollback = AsyncMock()
    registry = ToolRegistry(db, str(uuid.uuid4()))

    result, success, status, _ = run(
        registry.execute("record_weight", {"weight_kg": 500}, "我的体重是500公斤")
    )

    assert success is False
    assert status == "validation_error"
    assert result["error"] == "工具参数校验失败"


def test_runtime_blocks_duplicate_tool_calls_and_emits_live_trace():
    runtime = make_runtime()
    runtime._plan = AsyncMock(
        side_effect=[
            PlannerDecision(
                action="tool",
                tool="list_today_tasks",
                arguments={},
                reason="查询今日任务",
            ),
            PlannerDecision(
                action="tool",
                tool="list_today_tasks",
                arguments={},
                reason="再次查询",
            ),
        ]
    )
    runtime.registry.execute = AsyncMock(
        return_value=({"tasks": [], "count": 0}, True, "completed", 2)
    )
    emitted = []

    async def on_event(event):
        emitted.append(event)

    with patch("app.agent.runtime.ContextBuilder") as builder_cls:
        builder_cls.return_value.build_agent_context = AsyncMock(
            return_value=[{"role": "user", "content": "今天没有任务"}]
        )
        result = run(runtime.run("我今天有什么任务？", on_event=on_event))

    assert len(result.observations) == 1
    assert runtime.registry.execute.await_count == 1
    assert any(event.type == "guardrail" for event in result.trace)
    assert emitted == result.trace
    assert result.metrics["tool_calls"] == 1


def test_runtime_stops_after_confirmation_guardrail():
    runtime = make_runtime()
    runtime._plan = AsyncMock(
        return_value=PlannerDecision(
            action="tool",
            tool="skip_task",
            arguments={"dimension": "sleep"},
            reason="尝试跳过任务",
        )
    )

    with patch("app.agent.runtime.ContextBuilder") as builder_cls:
        builder_cls.return_value.build_agent_context = AsyncMock(
            return_value=[{"role": "user", "content": "请先确认"}]
        )
        result = run(runtime.run("我不想做睡眠任务"))

    assert len(result.observations) == 1
    assert result.observations[0].status == "approval_required"
    assert any(event.title == "需要用户确认" for event in result.trace)
