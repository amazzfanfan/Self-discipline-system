from __future__ import annotations

import inspect
import json
import logging
import re
import time
import uuid
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import ToolRegistry, has_explicit_completion, has_explicit_weight_record_intent
from app.agent.types import (
    AgentRunResult,
    AgentTraceEvent,
    PlannerDecision,
    ToolObservation,
)
from app.models.user import User
from app.services.context_builder import ContextBuilder
from app.services.llm_service import chat_completion_with_fallback
from app.services.agent_audit_service import (
    append_agent_event,
    create_pending_action,
    finish_agent_run,
    start_agent_run,
)


PLANNER_SYSTEM_PROMPT = """你是“系统”的任务编排器。你只负责选择下一步动作，不直接向用户输出长回复。

规则：
1. 只在确有必要时调用工具；普通咨询、鼓励或无需外部数据的问题选择 respond。
2. 每次最多选择一个工具，等待工具 Observation 后再决定下一步。
3. 不得把讨论、假设、否定句误判成执行指令。写操作必须来自用户当前消息的明确意图。
4. skip_task 属于有负面影响的操作，未出现明确“确认跳过”时不要调用。
5. 已有 Observation 足够回答时立即 respond；禁止重复相同工具和参数。
6. reason 只写一句可展示的动作理由，不输出隐含思维链。

只返回 JSON：
{"action":"tool|respond","tool":"工具名或null","arguments":{},"reason":"一句话理由"}
"""

TraceSink = Callable[[AgentTraceEvent], Awaitable[None] | None]
logger = logging.getLogger(__name__)


class AgentRuntime:
    MAX_STEPS = 4

    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.registry = ToolRegistry(db, str(user.id))
        self.llm_calls = 0
        self.audit_enabled = isinstance(db, AsyncSession)
        self.audit_run_id = None
        self.pending_action: dict[str, Any] | None = None

    async def run(
        self,
        user_message: str,
        on_event: TraceSink | None = None,
        user_message_id=None,
    ) -> AgentRunResult:
        run_id = uuid.uuid4().hex
        if self.audit_enabled:
            try:
                self.audit_run_id = await start_agent_run(run_id, self.user.id, user_message_id)
            except Exception:
                logger.exception("Failed to start Agent audit run")
        started = time.perf_counter()
        trace: list[AgentTraceEvent] = []
        observations: list[ToolObservation] = []
        seen_calls: set[str] = set()

        await self._emit(
            trace,
            AgentTraceEvent(
                type="status",
                title="已理解请求",
                detail="正在判断是否需要调用个人数据工具",
                step=0,
            ),
            on_event,
        )

        for step in range(1, self.MAX_STEPS + 1):
            decision = await self._plan(user_message, observations)
            await self._emit(
                trace,
                AgentTraceEvent(
                    type="plan",
                    title="规划下一步" if decision.action == "tool" else "信息已就绪",
                    detail=decision.reason,
                    step=step,
                    tool=decision.tool,
                ),
                on_event,
            )

            if decision.action == "respond" or not decision.tool:
                break

            call_key = f"{decision.tool}:{json.dumps(decision.arguments, sort_keys=True, ensure_ascii=False)}"
            if call_key in seen_calls:
                await self._emit(
                    trace,
                    AgentTraceEvent(
                        type="guardrail",
                        title="已阻止重复调用",
                        detail="相同工具和参数不会被重复执行",
                        step=step,
                        tool=decision.tool,
                        success=False,
                    ),
                    on_event,
                )
                break
            seen_calls.add(call_key)

            await self._emit(
                trace,
                AgentTraceEvent(
                    type="tool_call",
                    title=f"调用 {decision.tool}",
                    detail=self._short_json(decision.arguments),
                    step=step,
                    tool=decision.tool,
                ),
                on_event,
            )
            result, success, status, duration_ms = await self.registry.execute(
                decision.tool, decision.arguments, user_message
            )
            if status == "approval_required" and self.audit_enabled:
                try:
                    self.pending_action = await create_pending_action(
                        self.audit_run_id,
                        self.user.id,
                        decision.tool,
                        decision.arguments,
                        user_message,
                    )
                    result = {**result, "pending_action": self.pending_action}
                except Exception:
                    logger.exception("Failed to persist pending Agent action")
            observation = ToolObservation(
                tool=decision.tool,
                arguments=decision.arguments,
                result=result,
                success=success,
                status=status,
            )
            observations.append(observation)

            event_type = "guardrail" if status == "approval_required" else "tool_result"
            await self._emit(
                trace,
                AgentTraceEvent(
                    type=event_type,
                    title=(
                        "需要用户确认"
                        if status == "approval_required"
                        else ("工具执行完成" if success else "工具返回异常")
                    ),
                    detail=self._short_json(result),
                    step=step,
                    tool=decision.tool,
                    success=success,
                    duration_ms=duration_ms,
                ),
                on_event,
            )
            if status == "approval_required":
                break
        else:
            await self._emit(
                trace,
                AgentTraceEvent(
                    type="guardrail",
                    title="已达到执行上限",
                    detail=f"单次请求最多执行 {self.MAX_STEPS} 个步骤",
                    step=self.MAX_STEPS,
                    success=False,
                ),
                on_event,
            )

        context_builder = ContextBuilder(self.db, self.user)
        response_messages = await context_builder.build_agent_context(
            user_message=user_message,
            observations=[item.to_prompt_dict() for item in observations],
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        run_result = AgentRunResult(
            run_id=run_id,
            response_messages=response_messages,
            trace=trace,
            observations=observations,
            metrics={
                "planner_calls": self.llm_calls,
                "tool_calls": len(observations),
                "steps": max((event.step for event in trace), default=0),
                "planning_duration_ms": elapsed_ms,
                "status": "completed",
            },
            pending_action=self.pending_action,
        )
        if self.audit_run_id:
            try:
                await finish_agent_run(self.audit_run_id, run_result.metrics)
            except Exception:
                logger.exception("Failed to finish Agent audit run")
        return run_result

    async def _plan(
        self, user_message: str, observations: list[ToolObservation]
    ) -> PlannerDecision:
        if observations and any(item.status == "approval_required" for item in observations):
            return PlannerDecision(action="respond", reason="需要先取得用户明确确认")

        prompt_payload = {
            "current_request": user_message,
            "available_tools": self.registry.catalog(),
            "observations": [item.to_prompt_dict() for item in observations],
        }
        try:
            self.llm_calls += 1
            content = await chat_completion_with_fallback(
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
                ],
                temperature=0,
                max_tokens=400,
                response_format={"type": "json_object"},
                enable_thinking=False,
                num_retries=0,
                timeout=20,
            )
            decision = PlannerDecision.model_validate(self._parse_json(content))
            if decision.action == "tool" and not self.registry.has(decision.tool or ""):
                return PlannerDecision(action="respond", reason="没有适合当前请求的安全工具")
            return decision
        except Exception:
            return self._fallback_decision(user_message, observations)

    def _fallback_decision(
        self, message: str, observations: list[ToolObservation]
    ) -> PlannerDecision:
        if observations:
            return PlannerDecision(action="respond", reason="已获得工具结果")

        text = message.strip()
        weight_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:公斤|kg|千克)", text, re.IGNORECASE
        )
        if weight_match and has_explicit_weight_record_intent(text):
            return PlannerDecision(
                action="tool",
                tool="record_weight",
                arguments={"weight_kg": float(weight_match.group(1))},
                reason="记录用户明确提供的体重",
            )

        dimension = self._detect_dimension(text)
        if dimension and re.search(
            r"(?:我的目标是|设定.{0,6}目标|创建.{0,6}目标|"
            r"我(?:想要|希望|计划|打算|准备).{1,80})",
            text,
        ):
            return PlannerDecision(
                action="tool",
                tool="create_goal",
                arguments={"content": text, "goal_type": dimension},
                reason="用户明确提出了长期成长目标",
            )
        if dimension and has_explicit_completion(text):
            return PlannerDecision(
                action="tool",
                tool="complete_task",
                arguments={"dimension": dimension},
                reason="用户明确报告已完成任务",
            )
        if dimension and re.search(
            r"(?:确认.{0,8}跳过|跳过.{0,8}(?:确认|吧|掉)|明确跳过)", text
        ):
            return PlannerDecision(
                action="tool",
                tool="skip_task",
                arguments={"dimension": dimension},
                reason="用户已明确确认跳过任务",
            )
        if re.search(r"(?:今天|今日).{0,6}任务|任务.{0,6}(?:哪些|什么|情况)", text):
            return PlannerDecision(
                action="tool", tool="list_today_tasks", reason="查询今日任务"
            )
        if re.search(r"(?:评分|分数|成长状态)", text):
            return PlannerDecision(
                action="tool", tool="get_score_overview", reason="查询当前成长评分"
            )
        if re.search(
            r"(?:查看|列出|有哪些|我的).{0,8}目标|目标.{0,8}(?:情况|哪些)", text
        ):
            return PlannerDecision(
                action="tool", tool="list_goals", reason="查询当前成长目标"
            )
        return PlannerDecision(action="respond", reason="无需调用工具，直接回答")

    @staticmethod
    def _detect_dimension(text: str) -> str | None:
        keywords = {
            "exercise": ("运动", "跑步", "快走", "健身", "锻炼", "游泳"),
            "diet": ("饮食", "三餐", "吃饭", "餐食", "含糖饮料", "饮料", "蔬菜", "水果"),
            "sleep": ("睡眠", "睡觉", "早睡", "作息"),
            "appearance": ("护肤", "皮肤", "外貌", "形象"),
        }
        return next(
            (
                dimension
                for dimension, words in keywords.items()
                if any(word in text for word in words)
            ),
            None,
        )

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        cleaned = content.strip()
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE
        )
        return json.loads(cleaned)

    @staticmethod
    def _short_json(value: Any, limit: int = 360) -> str:
        text = json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= limit else f"{text[:limit]}…"

    async def _emit(
        self,
        trace: list[AgentTraceEvent],
        event: AgentTraceEvent,
        on_event: TraceSink | None,
    ) -> None:
        trace.append(event)
        if on_event:
            result = on_event(event)
            if inspect.isawaitable(result):
                await result
        if self.audit_run_id:
            try:
                await append_agent_event(self.audit_run_id, len(trace), event)
            except Exception:
                logger.exception("Failed to append Agent audit event")
