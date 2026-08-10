from __future__ import annotations

import inspect
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.score import UserScore
from app.services.cache_service import invalidate_scores, invalidate_tasks
from app.services.goal_service import goal_service
from app.services.memory_service import MemoryService
from app.services.task_service import (
    complete_task_by_dimension,
    get_today_tasks_dict,
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
                source="chat",
            )
            return {"success": True, "goal": goal.to_dict()}

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
            AgentTool("record_weight", "记录用户明确提供的当前体重", WeightArgs, save_weight, "write"),
            AgentTool("list_goals", "查询用户目标", GoalListArgs, list_goals),
            AgentTool(
                "create_goal",
                "当用户明确要求建立长期目标时创建目标",
                GoalCreateArgs,
                create_goal,
                "write",
            ),
            AgentTool("get_score_overview", "查询四个成长维度的当前评分", EmptyArgs, score_overview),
            AgentTool("search_memory", "检索与当前问题相关的历史偏好和事实", MemorySearchArgs, search_memory),
        ]
        for definition in definitions:
            self._register(definition)

    def _guard(self, tool: AgentTool, user_message: str) -> tuple[bool, str]:
        text = user_message.strip()
        if tool.name == "skip_task" and not re.search(
            r"(?:确认.{0,8}跳过|跳过.{0,8}(?:确认|吧|掉)|明确跳过)", text
        ):
            return False, "跳过任务会影响评分，请用户明确回复“确认跳过XX任务”后再执行。"
        if tool.name == "complete_task" and not has_explicit_completion(text):
            return False, "用户没有明确表示任务已经完成，禁止代替用户完成打卡。"
        if tool.name == "record_weight" and (
            not re.search(r"\d+(?:\.\d+)?", text)
            or not has_explicit_weight_record_intent(text)
        ):
            return False, "用户没有明确要求记录自己的体重。"
        if tool.name == "create_goal" and not re.search(
            r"(?:目标|计划|打算|想要|希望|准备)", text
        ):
            return False, "用户没有明确表达创建目标的意图。"
        return True, ""

    async def execute(
        self, name: str, arguments: dict[str, Any], user_message: str
    ) -> tuple[dict[str, Any], bool, str, int]:
        started = time.perf_counter()
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"未知工具: {name}"}, False, "error", 0

        allowed, reason = self._guard(tool, user_message)
        if not allowed:
            return {"message": reason, "requires_confirmation": True}, False, "approval_required", 0

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
