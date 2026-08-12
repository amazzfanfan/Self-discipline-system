from __future__ import annotations

import inspect
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal import Goal
from app.models.score import UserScore
from app.services.cache_service import invalidate_scores, invalidate_tasks
from app.services.goal_service import goal_service
from app.services.memory_service import MemoryService
from app.services.task_service import (
    complete_task_by_dimension,
    defer_task_by_dimension,
    get_today_tasks_dict,
    replace_task_by_dimension,
    resume_task_by_dimension,
    skip_task_by_dimension,
)
from app.services.weight_service import record_weight


logger = logging.getLogger(__name__)


COMPLETION_EVIDENCE_PATTERN = re.compile(
    r"(?:已经|已|刚刚|刚才).{0,10}(?:完成|做完|搞定|打卡)"
    r"|(?:完成|做完|搞定|打卡)(?:了|啦|成功|✅|$)"
    r"|(?:跑|练|锻炼|运动|快走|游泳)了"
)


def has_explicit_completion(text: str) -> bool:
    cleaned = text.strip()
    if re.search(r"(?:他|她|朋友|同事|别人).{0,12}(?:完成|做完|跑了|练了)", cleaned):
        return False
    return bool(COMPLETION_EVIDENCE_PATTERN.search(cleaned))


def has_explicit_weight_record_intent(text: str) -> bool:
    return bool(
        re.search(
            r"(?:帮我|请|给我)?.{0,6}(?:记录|记下).{0,10}(?:体重|公斤|kg)"
            r"|(?:我|本人).{0,8}(?:体重|称重|刚称).{0,8}\d",
            text,
            re.IGNORECASE,
        )
    )


class EmptyArgs(BaseModel):
    pass


class DimensionArgs(BaseModel):
    dimension: Literal["exercise", "diet", "sleep", "appearance"] = Field(
        description="任务维度"
    )


class WeightArgs(BaseModel):
    weight_kg: float = Field(gt=20, lt=300, description="公斤制体重")


class GoalListArgs(BaseModel):
    status: Literal["active", "completed", "paused"] | None = Field(
        default="active", description="目标状态"
    )


class GoalCreateArgs(BaseModel):
    content: str = Field(min_length=2, max_length=500, description="用户明确提出的目标")
    goal_type: Literal["exercise", "diet", "sleep", "appearance"] = Field(
        description="目标维度"
    )
    recurrence: Literal["flexible", "daily", "weekly", "custom"] | None = None
    days_of_week: list[int] | None = Field(default=None, max_length=7)
    preferred_time: clock_time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    reminder_enabled: bool | None = None


class TaskReplaceArgs(BaseModel):
    dimension: Literal["exercise", "diet", "sleep", "appearance"] = Field(
        description="要修改的今日任务维度"
    )
    title: str = Field(min_length=2, max_length=200, description="用户明确要求的新任务内容")
    reason: str | None = Field(default=None, max_length=500, description="修改原因")


class TaskScheduleArgs(DimensionArgs):
    mode: Literal["later", "reschedule", "excuse"] = Field(
        description="later=今天稍后提醒；reschedule=改到未来日期；excuse=今日免做"
    )
    deferred_until: datetime | None = Field(default=None, description="稍后提醒的具体时间")
    target_date: date | None = Field(default=None, description="改期后的日期")
    reason: str | None = Field(default=None, max_length=200, description="调整原因")


class GoalSelectorArgs(BaseModel):
    goal_keyword: str = Field(min_length=1, max_length=100, description="用于定位目标的关键词")


class GoalStatusArgs(GoalSelectorArgs):
    status: Literal["active", "completed", "paused"] = Field(description="目标的新状态")


class GoalUpdateArgs(GoalSelectorArgs):
    new_content: str = Field(min_length=2, max_length=500, description="修改后的完整目标内容")
    goal_type: Literal["exercise", "diet", "sleep", "appearance"] | None = None
    recurrence: Literal["flexible", "daily", "weekly", "custom"] | None = None
    days_of_week: list[int] | None = Field(default=None, max_length=7)
    preferred_time: clock_time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    reminder_enabled: bool | None = None


class MemorySearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    top_k: int = Field(default=3, ge=1, le=5)


ToolHandler = Callable[[BaseModel], Awaitable[dict[str, Any]]]


@dataclass
class AgentTool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    risk: Literal["read", "write", "destructive"] = "read"

    def prompt_spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "arguments_schema": self.args_model.model_json_schema(),
        }


class ToolRegistry:
    """User-scoped tool registry with schema validation and mutation guardrails."""

    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self._tools: dict[str, AgentTool] = {}
        self._register_defaults()

    def _register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def catalog(self) -> list[dict[str, Any]]:
        return [tool.prompt_spec() for tool in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def _register_defaults(self) -> None:
        async def resolve_goal(keyword: str) -> tuple[Goal | None, dict[str, Any] | None]:
            result = await self.db.execute(
                select(Goal)
                .where(Goal.user_id == self.user_id)
                .order_by(Goal.updated_at.desc(), Goal.created_at.desc())
            )
            goals = list(result.scalars().all())
            normalized = re.sub(r"\s+", "", keyword).lower()
            matches = [
                goal
                for goal in goals
                if normalized in re.sub(r"\s+", "", goal.content).lower()
            ]
            if not matches:
                return None, {"success": False, "message": f"没有找到包含“{keyword}”的目标"}
            if len(matches) > 1:
                return None, {
                    "success": False,
                    "message": "匹配到多个目标，请提供更具体的关键词",
                    "candidates": [goal.content for goal in matches[:5]],
                }
            return matches[0], None

        async def list_today(_: EmptyArgs) -> dict[str, Any]:
            tasks = await get_today_tasks_dict(self.db, self.user_id)
            return {"tasks": tasks, "count": len(tasks)}

        async def complete(args: DimensionArgs) -> dict[str, Any]:
            result = await complete_task_by_dimension(self.db, self.user_id, args.dimension)
            if result.get("success"):
                await self.db.commit()
                await invalidate_tasks(self.user_id)
                await invalidate_scores(self.user_id)
            return result

        async def skip(args: DimensionArgs) -> dict[str, Any]:
            result = await skip_task_by_dimension(self.db, self.user_id, args.dimension)
            if result.get("success"):
                await self.db.commit()
                await invalidate_tasks(self.user_id)
                await invalidate_scores(self.user_id)
            return result

        async def replace_task(args: TaskReplaceArgs) -> dict[str, Any]:
            result = await replace_task_by_dimension(
                self.db,
                self.user_id,
                args.dimension,
                args.title,
                args.reason,
            )
            if result.get("success"):
                await self.db.commit()
                await invalidate_tasks(self.user_id)
            return result

        async def defer_task(args: TaskScheduleArgs) -> dict[str, Any]:
            result = await defer_task_by_dimension(
                self.db,
                self.user_id,
                args.dimension,
                mode=args.mode,
                deferred_until=args.deferred_until,
                target_date=args.target_date,
                reason=args.reason,
            )
            if result.get("success"):
                await self.db.commit()
                await invalidate_tasks(self.user_id)
            return result

        async def resume_task(args: DimensionArgs) -> dict[str, Any]:
            result = await resume_task_by_dimension(self.db, self.user_id, args.dimension)
            if result.get("success"):
                await self.db.commit()
                await invalidate_tasks(self.user_id)
            return result

        async def save_weight(args: WeightArgs) -> dict[str, Any]:
            result = await record_weight(self.db, self.user_id, args.weight_kg)
            await self.db.commit()
            return {"success": True, **result}

        async def list_goals(args: GoalListArgs) -> dict[str, Any]:
            goals = await goal_service.get_user_goals(
                db=self.db, user_id=self.user_id, status=args.status
            )
            slim = [
                {
                    "id": goal["id"],
                    "content": goal["content"],
                    "goal_type": goal["goal_type"],
                    "status": goal["status"],
                }
                for goal in goals[:10]
            ]
            return {"goals": slim, "count": len(goals)}

        async def create_goal(args: GoalCreateArgs) -> dict[str, Any]:
            goal = await goal_service.create_goal(
                db=self.db,
                user_id=self.user_id,
                content=args.content,
                goal_type=args.goal_type,
                recurrence=args.recurrence,
                days_of_week=args.days_of_week,
                preferred_time=args.preferred_time,
                duration_minutes=args.duration_minutes,
                reminder_enabled=args.reminder_enabled,
                source="chat",
            )
            return {"success": True, "goal": goal.to_dict()}

        async def update_goal(args: GoalUpdateArgs) -> dict[str, Any]:
            goal, error = await resolve_goal(args.goal_keyword)
            if error:
                return error
            old_content = goal.content
            updates: dict[str, Any] = {"content": args.new_content}
            if args.goal_type:
                updates["goal_type"] = args.goal_type
            for field in (
                "recurrence",
                "days_of_week",
                "preferred_time",
                "duration_minutes",
                "reminder_enabled",
            ):
                value = getattr(args, field)
                if value is not None:
                    updates[field] = value
            updated = await goal_service.update_goal(
                db=self.db,
                goal_id=str(goal.id),
                user_id=self.user_id,
                updates=updates,
            )
            return {
                "success": bool(updated),
                "message": "目标已更新" if updated else "目标更新失败",
                "old_content": old_content,
                "goal": updated.to_dict() if updated else None,
            }

        async def change_goal_status(args: GoalStatusArgs) -> dict[str, Any]:
            goal, error = await resolve_goal(args.goal_keyword)
            if error:
                return error
            old_status = goal.status
            updated = await goal_service.update_goal(
                db=self.db,
                goal_id=str(goal.id),
                user_id=self.user_id,
                updates={"status": args.status},
            )
            return {
                "success": bool(updated),
                "message": "目标状态已更新" if updated else "目标状态更新失败",
                "content": goal.content,
                "old_status": old_status,
                "new_status": args.status,
            }

        async def delete_goal(args: GoalSelectorArgs) -> dict[str, Any]:
            goal, error = await resolve_goal(args.goal_keyword)
            if error:
                return error
            content = goal.content
            deleted = await goal_service.delete_goal(
                db=self.db,
                goal_id=str(goal.id),
                user_id=self.user_id,
            )
            return {
                "success": deleted,
                "message": "目标已删除" if deleted else "目标删除失败",
                "content": content,
            }

        async def score_overview(_: EmptyArgs) -> dict[str, Any]:
            result = await self.db.execute(
                select(UserScore).where(UserScore.user_id == self.user_id)
            )
            scores = [
                {
                    "dimension": score.dimension.value,
                    "score": float(score.score),
                    "streak_days": score.streak_days,
                }
                for score in result.scalars().all()
            ]
            return {"scores": scores}

        async def search_memory(args: MemorySearchArgs) -> dict[str, Any]:
            memories = await MemoryService(self.db).search_similar_memories(
                user_id=self.user_id,
                query=args.query,
                top_k=args.top_k,
                min_importance=0.2,
            )
            return {
                "memories": [
                    {
                        "content": memory["content"],
                        "memory_type": memory["memory_type"],
                        "relevance": memory.get("relevance_score", memory.get("similarity")),
                    }
                    for memory in memories
                ]
            }

        definitions = [
            AgentTool("list_today_tasks", "查询今天的任务及状态", EmptyArgs, list_today),
            AgentTool(
                "complete_task",
                "仅当用户明确表示已经完成某维度任务时，将今日任务标记完成",
                DimensionArgs,
                complete,
                "write",
            ),
            AgentTool(
                "skip_task",
                "跳过今日某维度任务并产生负向记录；必须要求用户明确确认",
                DimensionArgs,
                skip,
                "destructive",
            ),
            AgentTool(
                "replace_today_task",
                "当用户明确给出替代内容时，修改指定维度的今日未完成任务并真实写入数据库",
                TaskReplaceArgs,
                replace_task,
                "write",
            ),
            AgentTool(
                "defer_today_task",
                "调整今日任务：可在今天稍后提醒、改期到未来日期，或设为今日免做。必须明确 mode；later 还需 deferred_until，reschedule 还需 target_date",
                TaskScheduleArgs,
                defer_task,
                "write",
            ),
            AgentTool(
                "resume_today_task",
                "把今日暂缓的指定维度任务恢复为待完成",
                DimensionArgs,
                resume_task,
                "write",
            ),
            AgentTool("record_weight", "记录用户明确提供的当前体重", WeightArgs, save_weight, "write"),
            AgentTool("list_goals", "查询用户目标", GoalListArgs, list_goals),
            AgentTool(
                "create_goal",
                "当用户明确要求建立长期目标时创建目标",
                GoalCreateArgs,
                create_goal,
                "write",
            ),
            AgentTool(
                "update_goal",
                "根据关键词定位并修改一个已有成长目标；必须有修改后的完整内容",
                GoalUpdateArgs,
                update_goal,
                "write",
            ),
            AgentTool(
                "change_goal_status",
                "暂停、恢复或完成一个已有成长目标",
                GoalStatusArgs,
                change_goal_status,
                "write",
            ),
            AgentTool(
                "delete_goal",
                "永久删除一个已有成长目标；必须取得用户明确确认",
                GoalSelectorArgs,
                delete_goal,
                "destructive",
            ),
            AgentTool("get_score_overview", "查询四个成长维度的当前评分", EmptyArgs, score_overview),
            AgentTool("search_memory", "检索与当前问题相关的历史偏好和事实", MemorySearchArgs, search_memory),
        ]
        for definition in definitions:
            self._register(definition)

    def _guard(self, tool: AgentTool, user_message: str) -> tuple[bool, str, str]:
        text = user_message.strip()
        if tool.name == "skip_task" and not re.search(
            r"(?:确认.{0,8}跳过|跳过.{0,8}(?:确认|吧|掉)|明确跳过)", text
        ):
            return False, "跳过任务会影响评分，请用户明确回复“确认跳过XX任务”后再执行。", "approval_required"
        if tool.name == "delete_goal" and not re.search(
            r"(?:确认.{0,8}(?:删除|移除)|(?:删除|移除).{0,8}(?:确认|吧|掉)|确认删除目标)", text
        ):
            return False, "删除目标不可撤销，请明确确认后再执行。", "approval_required"
        if tool.name == "replace_today_task" and not re.search(
            r"(?:改成|改为|换成|换为|替换为|调整为)", text
        ):
            return False, "请先说明希望把该任务改成什么，再执行修改。", "clarification_required"
        if tool.name == "defer_today_task" and not re.search(
            r"(?:今日|今天).{0,8}(?:免做|不做|不安排|先不做)"
            r"|(?:改到|推迟到|挪到).{0,10}(?:明天|后天|\d{4}-\d{1,2}-\d{1,2})"
            r"|(?:一|1)\s*小时后|(?:今晚|今天).{0,4}\d{1,2}(?:点|:\d{2})",
            text,
        ):
            return (
                False,
                "请说明是今天几点再提醒、改到哪一天，还是设为今日免做。",
                "clarification_required",
            )
        if tool.name == "complete_task" and not has_explicit_completion(text):
            return False, "你还没有明确表示任务已经完成，因此本次没有打卡。", "clarification_required"
        if tool.name == "record_weight" and (
            not re.search(r"\d+(?:\.\d+)?", text)
            or not has_explicit_weight_record_intent(text)
        ):
            return False, "请明确提供要记录的体重数值。", "clarification_required"
        if tool.name == "create_goal" and not re.search(
            r"(?:目标|计划|打算|想要|希望|准备)", text
        ):
            return False, "请明确说明希望创建的成长目标。", "clarification_required"
        return True, "", ""

    async def execute(
        self, name: str, arguments: dict[str, Any], user_message: str
    ) -> tuple[dict[str, Any], bool, str, int]:
        started = time.perf_counter()
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"未知工具: {name}"}, False, "error", 0

        allowed, reason, guard_status = self._guard(tool, user_message)
        if not allowed:
            return {
                "message": reason,
                "requires_confirmation": guard_status == "approval_required",
                "requires_clarification": guard_status == "clarification_required",
            }, False, guard_status, 0

        try:
            parsed = tool.args_model.model_validate(arguments)
        except ValidationError as exc:
            return {
                "error": "工具参数校验失败",
                "details": exc.errors(include_url=False),
            }, False, "validation_error", int((time.perf_counter() - started) * 1000)

        try:
            result = tool.handler(parsed)
            if inspect.isawaitable(result):
                result = await result
            success = bool(result.get("success", True))
            return result, success, "completed" if success else "tool_error", int(
                (time.perf_counter() - started) * 1000
            )
        except Exception:
            logger.exception("Agent tool failed: %s", name)
            await self.db.rollback()
            return {"error": "工具执行失败，请稍后重试"}, False, "tool_error", int(
                (time.perf_counter() - started) * 1000
            )
