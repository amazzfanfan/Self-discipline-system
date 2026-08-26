from __future__ import annotations

import inspect
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import (
    ToolRegistry,
    extract_explicit_personal_fact,
    has_explicit_completion,
    has_explicit_goal_creation_intent,
    has_explicit_weight_record_intent,
    has_personal_memory_lookup_intent,
)
from app.agent.types import (
    AgentRunResult,
    AgentTraceEvent,
    PlannerDecision,
    ToolObservation,
)
from app.models.user import User
from app.core.time import local_now
from app.services.context_builder import ContextBuilder
from app.services.llm_service import chat_completion_with_fallback
from app.services.task_constraint_service import sanitize_constraint_phrase
from app.services.metrics_service import increment_metric
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
7. 用户只说“想修改任务/目标”但没有给出新内容或约束时选择 respond 并追问，禁止自行编造修改内容。
8. 明确的“每天/每周计划”应调用 create_goal；明确要求改成某项任务时应调用 replace_today_task。
9. 任务调整必须区分三种语义：今天具体时间再提醒用 later；改到明天或未来日期用 reschedule；明确今天不做但不希望受罚用 excuse。信息不足时追问，不得猜测。
10. 用户明确说明没有某个产品/器材、不能做某项活动或单项任务最长时间时，调用 update_task_constraints 持久化。
11. 用户明确报告某个目标的当前数值或进度增量时，调用 record_goal_progress；不得把计划值当成已完成进度。
12. observations 非空时，只有当前请求仍有明确未完成子任务或需要一次读取验证时才能继续调用工具；否则立即 respond。
13. 多工具工作流必须遵守先读后写、失败即停、不得重复写入。不得从 Observation 中扩展出用户没有要求的新目标。
14. 用户明确陈述自己的稳定个人事实或偏好时调用 remember_user_fact，并逐字使用当前消息，禁止推测或改写。

只返回 JSON：
{"action":"tool|respond","tool":"工具名或null","arguments":{},"reason":"一句话理由"}
"""

TraceSink = Callable[[AgentTraceEvent], Awaitable[None] | None]
logger = logging.getLogger(__name__)


class AgentRuntime:
    MAX_STEPS = 4
    MAX_TOOL_CALLS = 3
    MAX_WRITE_TOOL_CALLS = 2

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
        confirmed_action: dict[str, Any] | None = None,
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
        workflow_enabled = self._requires_multi_tool_workflow(user_message)
        write_tool_calls = 0
        partial_failure = False

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
            if confirmed_action and step == 1 and not observations:
                decision = PlannerDecision(
                    action="tool",
                    tool=str(confirmed_action["tool"]),
                    arguments=dict(confirmed_action.get("arguments") or {}),
                    reason="执行用户对上一条待确认操作的明确回复",
                )
            else:
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

            if len(observations) >= self.MAX_TOOL_CALLS:
                await self._emit(
                    trace,
                    AgentTraceEvent(
                        type="guardrail",
                        title="已达到工具上限",
                        detail=f"受控工作流单次最多调用 {self.MAX_TOOL_CALLS} 个工具",
                        step=step,
                        success=False,
                    ),
                    on_event,
                )
                break

            risk = self.registry.risk_of(decision.tool)
            if risk in {"write", "destructive"} and write_tool_calls >= self.MAX_WRITE_TOOL_CALLS:
                await self._emit(
                    trace,
                    AgentTraceEvent(
                        type="guardrail",
                        title="已阻止过多写操作",
                        detail=f"单次请求最多执行 {self.MAX_WRITE_TOOL_CALLS} 个数据修改工具",
                        step=step,
                        tool=decision.tool,
                        success=False,
                    ),
                    on_event,
                )
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
            pending_tool = decision.tool
            pending_arguments = decision.arguments
            pending_request = user_message
            proposed_action = result.get("proposed_action") if isinstance(result, dict) else None
            if success and status == "completed" and isinstance(proposed_action, dict):
                proposed_tool = proposed_action.get("tool")
                proposed_arguments = proposed_action.get("arguments")
                if self.registry.has(str(proposed_tool)) and isinstance(proposed_arguments, dict):
                    pending_tool = str(proposed_tool)
                    pending_arguments = proposed_arguments
                    pending_request = (
                        f"{user_message}\n系统已基于用户约束生成 AI 替代候选，等待用户确认"
                    )
                    status = "proposal_ready"
            if status in {"approval_required", "proposal_ready"} and self.audit_enabled:
                try:
                    self.pending_action = await create_pending_action(
                        self.audit_run_id,
                        self.user.id,
                        pending_tool,
                        pending_arguments,
                        pending_request,
                    )
                    result = {**result, "pending_action": self.pending_action}
                except Exception:
                    logger.exception("Failed to persist pending Agent action")
                    if status == "proposal_ready":
                        status = "completed"
            observation = ToolObservation(
                tool=decision.tool,
                arguments=decision.arguments,
                result=result,
                success=success,
                status=status,
            )
            observations.append(observation)
            if risk in {"write", "destructive"} and success:
                write_tool_calls += 1
            if not success and status not in {
                "approval_required",
                "clarification_required",
                "proposal_ready",
            }:
                partial_failure = bool(observations[:-1])

            guarded = status in {"approval_required", "clarification_required", "proposal_ready"}
            event_type = "guardrail" if guarded else "tool_result"
            await self._emit(
                trace,
                AgentTraceEvent(
                    type=event_type,
                    title=(
                        (
                            "等待确认 AI 替代任务"
                            if status == "proposal_ready"
                            else ("需要用户确认" if status == "approval_required" else "需要补充信息")
                        )
                        if guarded
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
            if guarded:
                break
            if not success or not workflow_enabled:
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

        direct_receipt_tools = {
            "list_today_tasks",
            "complete_task",
            "skip_task",
            "replace_today_task",
            "defer_today_task",
            "resume_today_task",
            "record_weight",
            "create_goal",
            "update_goal",
            "change_goal_status",
            "delete_goal",
            "update_task_constraints",
            "record_goal_progress",
            "remember_user_fact",
        }
        can_reply_without_context = len(observations) == 1 and (
            observations[0].tool in direct_receipt_tools
            or observations[0].status in {"approval_required", "clarification_required", "proposal_ready"}
        )
        if can_reply_without_context:
            response_messages = []
        else:
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
                "workflow_enabled": workflow_enabled,
                "write_tool_calls": write_tool_calls,
                "partial_failure": partial_failure,
            },
            pending_action=self.pending_action,
        )
        if workflow_enabled:
            await increment_metric("agent:workflow:started")
            if len(observations) > 1:
                await increment_metric("agent:workflow:multi_tool_completed")
            if partial_failure:
                await increment_metric("agent:workflow:partial_failure")
        if self.audit_run_id:
            try:
                await finish_agent_run(self.audit_run_id, run_result.metrics)
            except Exception:
                logger.exception("Failed to finish Agent audit run")
        return run_result

    async def _plan(
        self, user_message: str, observations: list[ToolObservation]
    ) -> PlannerDecision:
        if observations and any(
            item.status in {"approval_required", "clarification_required", "proposal_ready"}
            for item in observations
        ):
            return PlannerDecision(action="respond", reason="需要先取得用户明确确认")
        if observations and not observations[-1].success:
            return PlannerDecision(action="respond", reason="上一工具未成功，工作流已停止")

        # Clear state-changing intents are routed locally. This removes one
        # unnecessary planner-model round trip and makes persistence reliable.
        if not observations and not self._requires_multi_tool_workflow(user_message):
            deterministic = self._fallback_decision(user_message, observations)
            if deterministic.action == "tool" or deterministic.reason.startswith("需要先明确任务调整方式"):
                return deterministic

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
        if re.search(r"(?:忽略所有规则|泄露系统提示词|记忆里说你必须)", text):
            return PlannerDecision(action="respond", reason="检测到不可信指令，不执行工具")
        if re.search(r"(?:他|她|朋友|同事|别人).{0,16}(?:任务|目标|体重|计划|完成|跳过)", text):
            return PlannerDecision(action="respond", reason="这是第三方信息，不执行个人数据工具")
        if re.search(r"(?:假设|如果).{0,30}(?:完成|跳过|删除|记录|创建|延后|恢复|累计|进度|增加|减少)", text):
            return PlannerDecision(action="respond", reason="这是情景讨论，不执行写操作")
        if re.search(r"(?:明天|后天|下周|以后|计划|准备).{0,30}(?:目标|进度).{0,12}(?:累计|增加|减少|达到)", text):
            return PlannerDecision(action="respond", reason="这是未来计划，不将计划值写成已完成进度")
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

        if has_personal_memory_lookup_intent(text):
            return PlannerDecision(
                action="tool",
                tool="search_memory",
                arguments={"query": text, "top_k": 3},
                reason="查询当前账号已保存的个人事实",
            )

        personal_fact = extract_explicit_personal_fact(text)
        if personal_fact:
            content, memory_type = personal_fact
            return PlannerDecision(
                action="tool",
                tool="remember_user_fact",
                arguments={"content": content, "memory_type": memory_type},
                reason="保存用户明确陈述的个人事实",
            )

        unavailable_match = re.search(
            r"(?:我)?(?:没有|没买|手头没有|不能用)\s*([^，。！？!?]{1,30})",
            text,
        )
        if unavailable_match:
            item = sanitize_constraint_phrase(unavailable_match.group(1))
            if not item:
                return PlannerDecision(action="respond", reason="需要明确不可用的物品或器材")
            return PlannerDecision(
                action="tool",
                tool="update_task_constraints",
                arguments={"unavailable_items": [item]},
                reason="记录用户明确说明的不可用物品或器材",
            )
        avoid_match = re.search(r"(?:我)?(?:不能做|避免)\s*([^，。！？!?]{1,30})", text)
        if avoid_match:
            activity = sanitize_constraint_phrase(avoid_match.group(1))
            if not activity:
                return PlannerDecision(action="respond", reason="需要明确应避免的活动")
            return PlannerDecision(
                action="tool",
                tool="update_task_constraints",
                arguments={"avoid_activities": [activity]},
                reason="记录用户明确说明需要避免的活动",
            )
        available_match = re.search(
            r"(?:我有(?!哪些|什么|几)|我可以使用|可用)\s*([^，。！？!?]{1,30})",
            text,
        )
        if available_match:
            item = sanitize_constraint_phrase(available_match.group(1))
            if not item:
                return PlannerDecision(action="respond", reason="需要明确可用的物品或器材")
            return PlannerDecision(
                action="tool",
                tool="update_task_constraints",
                arguments={"available_items": [item]},
                reason="记录用户明确说明的可用物品或器材",
            )
        max_minutes_match = re.search(r"(?:任务)?最多\s*(\d{1,3})\s*分钟", text)
        if max_minutes_match:
            return PlannerDecision(
                action="tool",
                tool="update_task_constraints",
                arguments={"max_task_minutes": int(max_minutes_match.group(1))},
                reason="记录用户的单项任务时长上限",
            )

        goal_progress_match = re.search(
            r"(.{1,30}?)(?:目标|计划).{0,12}?"
            r"(进度(?:增加|提升|减少|降低)|(?:目前|现在)?(?:累计|完成到|达到|进度是))\s*"
            r"(\d+(?:\.\d+)?)",
            text,
        )
        if goal_progress_match:
            keyword = goal_progress_match.group(1).strip(" ，。！？!?：:的")
            operation = goal_progress_match.group(2)
            value = float(goal_progress_match.group(3))
            if "增加" in operation or "提升" in operation:
                arguments = {"goal_keyword": keyword, "delta": value}
            elif "减少" in operation or "降低" in operation:
                arguments = {"goal_keyword": keyword, "delta": -value}
            else:
                arguments = {"goal_keyword": keyword, "current_value": value}
            return PlannerDecision(
                action="tool",
                tool="record_goal_progress",
                arguments=arguments,
                reason="记录用户明确报告的目标数值进度",
            )

        dimension = self._detect_dimension(text)
        goal_update_match = re.search(
            r"(?:把|将)\s*(.{1,60}?)(?:目标|计划)\s*(?:改成|改为|更新为|调整为)\s*(.{2,220})",
            text,
        )
        if goal_update_match:
            new_content = goal_update_match.group(2).strip("。！？!? ")
            return PlannerDecision(
                action="tool",
                tool="update_goal",
                arguments={
                    "goal_keyword": goal_update_match.group(1).strip(),
                    "new_content": new_content,
                    "goal_type": self._detect_dimension(new_content),
                },
                reason="更新用户明确指定的成长目标",
            )
        replacement_match = re.search(
            r"(?:把|将)?(?:今天的|今日)?(?:运动|饮食|睡眠|形象管理|形象|护肤)?任务"
            r".{0,10}?(?:改成|改为|换成|换为|替换为|调整为)\s*(.{2,180})",
            text,
        )
        if dimension and replacement_match:
            replacement = replacement_match.group(1).strip("。！？!? ")
            source_text = re.split(
                r"(?:改成|改为|换成|换为|替换为|调整为)", text, maxsplit=1
            )[0]
            task_keyword = self._extract_task_keyword(source_text)
            return PlannerDecision(
                action="tool",
                tool="replace_today_task",
                arguments={
                    "dimension": dimension,
                    "title": replacement,
                    "reason": "根据用户在对话中明确提出的新任务进行替换",
                    **({"task_keyword": task_keyword} if task_keyword else {}),
                },
                reason="更新用户明确指定的今日任务",
            )

        if dimension and has_explicit_goal_creation_intent(text):
            goal_content = re.sub(
                r"^(?:请)?(?:帮我)?(?:创建|设定|新增)(?:一个)?(?:成长|长期)?目标\s*[：:]?\s*"
                r"|^我的目标是\s*|^我(?:想要|希望|计划|打算|准备)\s*",
                "",
                text,
            ).strip()
            goal_content = re.sub(r"[吧呀啊]?[。！？!?]*$", "", goal_content).strip()
            arguments: dict[str, Any] = {
                "content": goal_content or text,
                "goal_type": dimension,
            }
            absolute_weight = re.search(
                r"(?:体重.{0,8}(?:到|至|目标为)|(?:减重|增重)到|目标体重(?:是|为)?)\s*(\d+(?:\.\d+)?)\s*(?:公斤|kg|千克)",
                text,
                re.IGNORECASE,
            )
            if absolute_weight:
                current_weight = getattr(getattr(self.user, "profile", None), "weight_kg", None)
                direction = "increase" if re.search(r"(?:增重|增加)", text) else "decrease"
                arguments.update(
                    {
                        "target_metric": "体重",
                        "target_unit": "kg",
                        "metric_direction": direction,
                        "target_value": float(absolute_weight.group(1)),
                        "baseline_value": float(current_weight) if current_weight is not None else None,
                        "current_value": float(current_weight) if current_weight is not None else None,
                    }
                )
            return PlannerDecision(
                action="tool",
                tool="create_goal",
                arguments=arguments,
                reason="用户明确提出了长期成长目标",
            )

        goal_keyword = self._extract_goal_keyword(text)
        if goal_keyword and re.search(r"(?:暂停|先停一下|停止)\S{0,8}(?:目标|计划)?|(?:目标|计划).{0,8}暂停", text):
            return PlannerDecision(
                action="tool",
                tool="change_goal_status",
                arguments={"goal_keyword": goal_keyword, "status": "paused"},
                reason="暂停用户指定的成长目标",
            )
        if goal_keyword and re.search(r"(?:恢复|继续|重新开始).{0,12}(?:目标|计划)", text):
            return PlannerDecision(
                action="tool",
                tool="change_goal_status",
                arguments={"goal_keyword": goal_keyword, "status": "active"},
                reason="恢复用户指定的成长目标",
            )
        if goal_keyword and re.search(r"(?:完成|结束).{0,12}(?:目标|计划)|(?:目标|计划).{0,8}(?:完成|达成)", text):
            return PlannerDecision(
                action="tool",
                tool="change_goal_status",
                arguments={"goal_keyword": goal_keyword, "status": "completed"},
                reason="完成用户指定的成长目标",
            )
        if goal_keyword and re.search(r"(?:删除|移除|取消).{0,12}(?:目标|计划)|(?:目标|计划).{0,8}(?:删除|移除)", text):
            return PlannerDecision(
                action="tool",
                tool="delete_goal",
                arguments={"goal_keyword": goal_keyword},
                reason="删除用户指定的成长目标",
            )
        if dimension and has_explicit_completion(text):
            task_keyword = self._extract_task_keyword(text)
            return PlannerDecision(
                action="tool",
                tool="complete_task",
                arguments={
                    "dimension": dimension,
                    **({"task_keyword": task_keyword} if task_keyword else {}),
                },
                reason="用户明确报告已完成任务",
            )
        if dimension and re.search(r"(?:恢复|继续).{0,10}(?:任务|待办)|(?:任务|待办).{0,8}(?:恢复|继续)", text):
            task_keyword = self._extract_task_keyword(text)
            return PlannerDecision(
                action="tool",
                tool="resume_today_task",
                arguments={
                    "dimension": dimension,
                    **({"task_keyword": task_keyword} if task_keyword else {}),
                },
                reason="恢复今日暂缓任务",
            )

        if dimension and re.search(r"(?:今日|今天).{0,6}(?:免做|不做|不安排|先不做)", text):
            task_keyword = self._extract_task_keyword(text)
            return PlannerDecision(
                action="tool",
                tool="defer_today_task",
                arguments={
                    "dimension": dimension,
                    "mode": "excuse",
                    **({"task_keyword": task_keyword} if task_keyword else {}),
                },
                reason="将任务设为今日免做且不计入完成率",
            )
        if dimension and re.search(r"(?:改到|推迟到|挪到).{0,8}(?:明天|后天|\d{4}-\d{1,2}-\d{1,2})", text):
            now = local_now()
            if "后天" in text:
                target_date = now.date() + timedelta(days=2)
            elif "明天" in text:
                target_date = now.date() + timedelta(days=1)
            else:
                date_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", text)
                target_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
            return PlannerDecision(
                action="tool",
                tool="defer_today_task",
                arguments={
                    "dimension": dimension,
                    "mode": "reschedule",
                    "target_date": target_date.isoformat(),
                    **(
                        {"task_keyword": self._extract_task_keyword(text)}
                        if self._extract_task_keyword(text)
                        else {}
                    ),
                },
                reason="将今日任务改期到用户指定日期",
            )
        if dimension and re.search(r"(?:一|1)\s*小时后", text):
            wake_at = local_now() + timedelta(hours=1)
            if wake_at.date() != local_now().date():
                return PlannerDecision(
                    action="respond",
                    reason="需要先明确任务调整方式：一小时后将跨日，请改为选择未来日期",
                )
            return PlannerDecision(
                action="tool",
                tool="defer_today_task",
                arguments={
                    "dimension": dimension,
                    "mode": "later",
                    "deferred_until": wake_at.isoformat(),
                    **(
                        {"task_keyword": self._extract_task_keyword(text)}
                        if self._extract_task_keyword(text)
                        else {}
                    ),
                },
                reason="按用户指定的一小时后重新提醒",
            )
        if dimension and re.search(r"(?:今晚|今天).{0,4}\d{1,2}(?:点|:\d{2})", text):
            now = local_now()
            time_match = re.search(r"(\d{1,2})(?:点|:(\d{2}))", text)
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            wake_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return PlannerDecision(
                action="tool",
                tool="defer_today_task",
                arguments={
                    "dimension": dimension,
                    "mode": "later",
                    "deferred_until": wake_at.isoformat(),
                    **(
                        {"task_keyword": self._extract_task_keyword(text)}
                        if self._extract_task_keyword(text)
                        else {}
                    ),
                },
                reason="按用户指定的今天时间重新提醒",
            )
        if dimension and re.search(r"(?:延后|暂缓|稍后再做|晚点再做).{0,10}(?:任务)?|(?:任务).{0,8}(?:延后|暂缓)", text):
            return PlannerDecision(
                action="respond",
                reason="需要先明确任务调整方式：今天几点提醒、改到哪天，还是今日免做",
            )
        if dimension and re.search(r"(?:跳过|放弃).{0,12}(?:任务)?|(?:任务).{0,8}(?:跳过|放弃)", text):
            task_keyword = self._extract_task_keyword(text)
            return PlannerDecision(
                action="tool",
                tool="skip_task",
                arguments={
                    "dimension": dimension,
                    **({"task_keyword": task_keyword} if task_keyword else {}),
                },
                reason="处理用户跳过今日任务的请求",
            )
        if re.search(
            r"(?:当前|今天|今日).{0,10}(?:哪些|什么|所有|全部)?任务"
            r"|我(?:当前)?有(?:哪些|什么)?任务|有哪些任务|任务.{0,8}(?:哪些|什么|情况)",
            text,
        ):
            return PlannerDecision(
                action="tool", tool="list_today_tasks", reason="查询今日任务"
            )
        if re.search(r"(?:评分|分数|成长状态)", text):
            return PlannerDecision(
                action="tool", tool="get_score_overview", reason="查询当前成长评分"
            )
        if re.search(r"(?:完成率|行为动量|执行表现|执行情况|最近表现|行为趋势|打卡情况)", text):
            return PlannerDecision(
                action="tool",
                tool="get_behavior_overview",
                reason="查询近期行为表现与今日状态",
            )
        if re.search(r"(?:体重).{0,8}(?:趋势|历史|变化|均值)|(?:最近).{0,8}(?:体重)", text):
            return PlannerDecision(
                action="tool",
                tool="get_weight_trend",
                reason="查询近期体重趋势",
            )
        if re.search(
            r"(?:查看|列出|有哪些|我的).{0,8}目标|目标.{0,8}(?:情况|哪些)", text
        ):
            return PlannerDecision(
                action="tool", tool="list_goals", reason="查询当前成长目标"
            )
        return PlannerDecision(action="respond", reason="无需调用工具，直接回答")

    @staticmethod
    def _requires_multi_tool_workflow(text: str) -> bool:
        """Conservatively enable iterative planning only for compound requests."""
        connectors = bool(
            re.search(r"(?:并且|同时|然后|之后|以后再|接着|另外|以及|再帮我|并把|并将|和|及)", text)
        )
        action_groups = sum(
            bool(re.search(pattern, text))
            for pattern in (
                r"(?:查询|看看|列出|有哪些|根据|分析)",
                r"(?:创建|新增|设定).{0,8}(?:目标|计划)",
                r"(?:修改|更新|调整|改成|换成|换掉|替换)",
                r"(?:完成|打卡|记录).{0,12}(?:任务|目标|进度|体重)",
                r"(?:暂停|恢复|删除|跳过|延后|改期)",
                r"(?:没有|不能|不适合|最多).{0,20}(?:物品|器材|眼霜|活动|分钟|任务)",
            )
        )
        data_driven_change = bool(
            re.search(r"(?:根据|结合).{0,20}(?:最近|本周|数据|完成情况|反馈).{0,30}(?:调整|修改|安排|建议)", text)
        )
        referenced_objects = sum(
            keyword in text
            for keyword in ("任务", "目标", "评分", "记忆", "体重", "趋势", "完成率", "Check-in")
        )
        return data_driven_change or (
            connectors and (action_groups >= 2 or referenced_objects >= 2)
        )

    @staticmethod
    def _detect_dimension(text: str) -> str | None:
        keywords = {
            "exercise": (
                "运动", "跑步", "快走", "健身", "锻炼", "游泳",
                "爬坡", "拉伸", "瑜伽", "骑行", "力量训练", "遛狗", "散步",
            ),
            "diet": (
                "饮食", "三餐", "吃饭", "餐食", "含糖饮料", "饮料", "蔬菜", "水果",
                "体重", "减重", "增重", "减脂",
            ),
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
    def _extract_goal_keyword(text: str) -> str | None:
        if "目标" not in text and "计划" not in text:
            return None
        cleaned = re.sub(
            r"(?:请|帮我|把|将|我的|这个|那个|成长|长期|目标|计划|暂停|停止|恢复|继续|重新开始|完成|达成|结束|删除|移除|取消|确认)",
            " ",
            text,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，。！？!?：:的")
        return cleaned[:80] or None

    @staticmethod
    def _extract_task_keyword(text: str) -> str | None:
        """Keep the task-specific phrase so same-dimension tasks remain addressable."""
        cleaned = re.sub(
            r"(?:请|帮我|把|将|我的|我|这个|那个|今天的|今日的|今天|今日|今晚|"
            r"任务|待办|已经|刚刚|刚才|完成|做完|搞定|打卡|跳过|放弃|"
            r"恢复|继续|免做|不做|不安排|先不做|延后|暂缓|稍后再做|晚点再做|"
            r"改一下|修改|更改|调整|提醒|做|"
            r"改到|推迟到|挪到|一小时后|1小时后|明天|后天|"
            r"运动|锻炼|饮食|睡眠|形象管理|形象|护肤|确认|了|啦|成功)",
            " ",
            text,
        )
        cleaned = re.sub(r"\d{1,2}(?:点|:\d{2})|\d{4}-\d{1,2}-\d{1,2}", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，。！？!?：:的")
        return cleaned[:100] if len(cleaned) >= 2 else None

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
