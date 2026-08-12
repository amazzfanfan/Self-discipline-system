"""
Goals Router - 目标管理 API
提供目标的创建、查询、更新、删除和搜索功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from datetime import date, time, timedelta
from typing import Literal, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.behavior import DailyCheckIn
from app.models.task import Task
from app.services.goal_service import goal_service
from app.core.time import local_today
from app.services.adaptive_task_service import choose_task_budget
from app.services.goal_schedule_service import goal_is_due
from app.services.goal_progress_service import (
    build_goal_progress_summaries,
    get_goal_progress_timeline,
    apply_manual_goal_progress,
)

router = APIRouter(prefix="/api/goals", tags=["goals"])


# ── Pydantic 请求/响应模型 ──────────────────────────────────────────

class GoalMilestoneRequest(BaseModel):
    id: Optional[str] = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=100)
    target_value: float = Field(ge=0)
    completed_at: Optional[str] = None


class GoalCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="目标内容")
    goal_type: Literal["exercise", "diet", "sleep", "appearance"] = Field(
        default="exercise", description="目标类型: exercise/diet/sleep/appearance"
    )
    structured_data: Optional[dict] = Field(default=None, description="结构化数据")
    target_metric: Optional[str] = Field(default=None, max_length=100)
    target_unit: Optional[str] = Field(default=None, max_length=30)
    metric_direction: Literal["increase", "decrease"] = "increase"
    target_value: Optional[float] = Field(default=None, gt=0)
    baseline_value: Optional[float] = Field(default=None, ge=0)
    current_value: Optional[float] = Field(default=None, ge=0)
    deadline: Optional[date] = None
    milestones: list[GoalMilestoneRequest] = Field(default_factory=list, max_length=20)
    recurrence: Literal["flexible", "daily", "weekly", "custom"] | None = None
    days_of_week: list[Literal[0, 1, 2, 3, 4, 5, 6]] | None = Field(
        default=None, max_length=7
    )
    preferred_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    start_date: Optional[date] = None
    reminder_enabled: Optional[bool] = None
    reminder_minutes_before: int = Field(default=30, ge=0, le=1440)
    progress_mode: Literal["sessions", "manual"] = "sessions"


class GoalUpdateRequest(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=2000, description="目标内容")
    goal_type: Optional[Literal["exercise", "diet", "sleep", "appearance"]] = Field(
        default=None, description="目标类型"
    )
    status: Optional[Literal["active", "completed", "paused"]] = Field(
        default=None, description="目标状态: active/completed/paused"
    )
    importance_score: Optional[float] = Field(default=None, ge=0, le=1, description="重要性评分")
    structured_data: Optional[dict] = Field(default=None, description="结构化数据")
    target_metric: Optional[str] = Field(default=None, max_length=100)
    target_unit: Optional[str] = Field(default=None, max_length=30)
    metric_direction: Optional[Literal["increase", "decrease"]] = None
    target_value: Optional[float] = Field(default=None, gt=0)
    baseline_value: Optional[float] = Field(default=None, ge=0)
    current_value: Optional[float] = Field(default=None, ge=0)
    deadline: Optional[date] = None
    milestones: Optional[list[GoalMilestoneRequest]] = Field(default=None, max_length=20)
    recurrence: Optional[Literal["flexible", "daily", "weekly", "custom"]] = None
    days_of_week: Optional[list[Literal[0, 1, 2, 3, 4, 5, 6]]] = Field(
        default=None, max_length=7
    )
    preferred_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    start_date: Optional[date] = None
    reminder_enabled: Optional[bool] = None
    reminder_minutes_before: Optional[int] = Field(default=None, ge=0, le=1440)
    progress_mode: Optional[Literal["sessions", "manual"]] = None


class GoalResponse(BaseModel):
    id: str
    user_id: str
    content: str
    goal_type: str
    structured_data: Optional[dict] = None
    target_metric: Optional[str] = None
    target_unit: Optional[str] = None
    metric_direction: str
    target_value: Optional[float] = None
    baseline_value: Optional[float] = None
    current_value: Optional[float] = None
    deadline: Optional[str] = None
    milestones: list[dict] = Field(default_factory=list)
    recurrence: str
    days_of_week: list[int] = Field(default_factory=list)
    preferred_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    start_date: Optional[str] = None
    reminder_enabled: bool
    reminder_minutes_before: int
    progress_mode: str
    completed_sessions: int
    last_progress_at: Optional[str] = None
    importance_score: Optional[float] = None
    status: str
    source: str
    created_at: str
    updated_at: Optional[str] = None


class GoalProgressRequest(BaseModel):
    current_value: Optional[float] = Field(default=None, ge=0)
    delta: Optional[float] = None
    note: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def require_exactly_one_progress_value(self):
        if (self.current_value is None) == (self.delta is None):
            raise ValueError("current_value and delta must provide exactly one value")
        return self


# ── API 端点 ────────────────────────────────────────────────────────

@router.post("", response_model=GoalResponse)
async def create_goal(
    body: GoalCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """创建目标"""
    goal = await goal_service.create_goal(
        db=db,
        user_id=str(user.id),
        content=body.content,
        goal_type=body.goal_type,
        structured_data=body.structured_data,
        target_metric=body.target_metric,
        target_unit=body.target_unit,
        metric_direction=body.metric_direction,
        target_value=body.target_value,
        baseline_value=body.baseline_value,
        current_value=body.current_value,
        deadline=body.deadline,
        milestones=[item.model_dump() for item in body.milestones],
        recurrence=body.recurrence,
        days_of_week=body.days_of_week,
        preferred_time=body.preferred_time,
        duration_minutes=body.duration_minutes,
        start_date=body.start_date,
        reminder_enabled=body.reminder_enabled,
        reminder_minutes_before=body.reminder_minutes_before,
        progress_mode=body.progress_mode,
        source="manual",
    )
    return goal.to_dict()


@router.get("")
async def list_goals(
    status: Optional[Literal["active", "completed", "paused"]] = Query(default=None, description="按状态过滤"),
    goal_type: Optional[Literal["exercise", "diet", "sleep", "appearance"]] = Query(default=None, description="按类型过滤"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """获取目标列表"""
    goals = await goal_service.get_user_goals(
        db=db,
        user_id=str(user.id),
        status=status,
        goal_type=goal_type,
    )
    return goals


@router.get("/search")
async def search_goals(
    query: str = Query(..., min_length=1, description="搜索关键词"),
    top_k: int = Query(default=5, ge=1, le=20, description="返回数量"),
    status: Optional[Literal["active", "completed", "paused"]] = Query(default=None, description="按状态过滤"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """搜索目标（语义搜索 + 关键词降级）"""
    goals = await goal_service.search_goals(
        db=db,
        user_id=str(user.id),
        query=query,
        top_k=top_k,
        status=status,
    )
    return goals


@router.get("/progress/summary")
async def goal_progress_summary(
    week_start: Optional[date] = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Return one-query execution summaries for all goals in a week."""
    today = local_today()
    start = week_start or (today - timedelta(days=today.weekday()))
    end = start + timedelta(days=6)
    return await build_goal_progress_summaries(
        db,
        user.id,
        period_start=start,
        period_end=end,
        as_of=min(today, end),
    )


@router.get("/planning-status")
async def goal_planning_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Explain which due goals entered today's finite task budget."""
    today = local_today()
    active_goals = await goal_service.get_user_goals(
        db=db,
        user_id=str(user.id),
        status="active",
    )
    due_goals = [goal for goal in active_goals if goal_is_due(goal, today)]
    linked_goal_ids = {
        str(value)
        for value in (
            await db.execute(
                select(Task.goal_id).where(
                    Task.user_id == user.id,
                    Task.scheduled_date == today,
                    Task.goal_id.isnot(None),
                )
            )
        ).scalars().all()
        if value
    }
    checkin = await db.scalar(
        select(DailyCheckIn).where(
            DailyCheckIn.user_id == user.id,
            DailyCheckIn.checkin_date == today,
        )
    )
    configured_budget = int(user.profile.daily_task_budget if user.profile else 3)
    effective_budget = choose_task_budget(configured_budget, checkin)
    queued = [
        {
            "id": goal["id"],
            "content": goal["content"],
            "goal_type": goal["goal_type"],
            "reason": "今日任务容量不足，将按最近执行时间公平轮换",
        }
        for goal in due_goals
        if goal["id"] not in linked_goal_ids
    ]
    return {
        "date": today.isoformat(),
        "configured_budget": configured_budget,
        "effective_budget": effective_budget,
        "due_goal_count": len(due_goals),
        "scheduled_goal_count": sum(goal["id"] in linked_goal_ids for goal in due_goals),
        "queued_goal_count": len(queued),
        "over_capacity": bool(queued),
        "queued_goals": queued,
    }


@router.get("/{goal_id}/progress")
async def goal_progress_timeline(
    goal_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    timeline = await get_goal_progress_timeline(
        db,
        user.id,
        goal_id,
        limit=limit,
    )
    if timeline is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return timeline


@router.post("/{goal_id}/progress")
async def record_goal_progress(
    goal_id: str,
    body: GoalProgressRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    try:
        result = await apply_manual_goal_progress(
            db,
            goal_id=goal_id,
            user_id=user.id,
            current_value=body.current_value,
            delta=body.delta,
            note=body.note,
            source="goal_progress_api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return result


@router.put("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: str,
    body: GoalUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """更新目标"""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    required_fields = (
        "content",
        "goal_type",
        "status",
        "recurrence",
        "reminder_enabled",
        "reminder_minutes_before",
        "progress_mode",
    )
    if any(updates.get(field) is None for field in required_fields if field in updates):
        raise HTTPException(status_code=422, detail="required goal fields cannot be null")

    goal = await goal_service.update_goal(
        db=db,
        goal_id=goal_id,
        user_id=str(user.id),
        updates=updates,
    )
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal.to_dict()


@router.delete("/{goal_id}")
async def delete_goal(
    goal_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """删除目标"""
    deleted = await goal_service.delete_goal(
        db=db,
        goal_id=goal_id,
        user_id=str(user.id),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"message": "Goal deleted", "id": goal_id}
