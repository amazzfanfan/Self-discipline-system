"""
Goals Router - 目标管理 API
提供目标的创建、查询、更新、删除和搜索功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import date, time
from typing import Literal, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.goal_service import goal_service

router = APIRouter(prefix="/api/goals", tags=["goals"])


# ── Pydantic 请求/响应模型 ──────────────────────────────────────────

class GoalCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="目标内容")
    goal_type: Literal["exercise", "diet", "sleep", "appearance"] = Field(
        default="exercise", description="目标类型: exercise/diet/sleep/appearance"
    )
    structured_data: Optional[dict] = Field(default=None, description="结构化数据")
    target_metric: Optional[str] = Field(default=None, max_length=100)
    target_value: Optional[float] = Field(default=None, gt=0)
    current_value: Optional[float] = Field(default=None, ge=0)
    deadline: Optional[date] = None
    milestones: list[dict] = Field(default_factory=list, max_length=20)
    recurrence: Literal["flexible", "daily", "weekly", "custom"] | None = None
    days_of_week: list[Literal[0, 1, 2, 3, 4, 5, 6]] | None = Field(
        default=None, max_length=7
    )
    preferred_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    start_date: Optional[date] = None
    reminder_enabled: Optional[bool] = None
    reminder_minutes_before: int = Field(default=30, ge=0, le=1440)


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
    target_value: Optional[float] = Field(default=None, gt=0)
    current_value: Optional[float] = Field(default=None, ge=0)
    deadline: Optional[date] = None
    milestones: Optional[list[dict]] = Field(default=None, max_length=20)
    recurrence: Optional[Literal["flexible", "daily", "weekly", "custom"]] = None
    days_of_week: Optional[list[Literal[0, 1, 2, 3, 4, 5, 6]]] = Field(
        default=None, max_length=7
    )
    preferred_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    start_date: Optional[date] = None
    reminder_enabled: Optional[bool] = None
    reminder_minutes_before: Optional[int] = Field(default=None, ge=0, le=1440)


class GoalResponse(BaseModel):
    id: str
    user_id: str
    content: str
    goal_type: str
    structured_data: Optional[dict] = None
    target_metric: Optional[str] = None
    target_value: Optional[float] = None
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
    importance_score: Optional[float] = None
    status: str
    source: str
    created_at: str
    updated_at: Optional[str] = None


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
        target_value=body.target_value,
        current_value=body.current_value,
        deadline=body.deadline,
        milestones=body.milestones,
        recurrence=body.recurrence,
        days_of_week=body.days_of_week,
        preferred_time=body.preferred_time,
        duration_minutes=body.duration_minutes,
        start_date=body.start_date,
        reminder_enabled=body.reminder_enabled,
        reminder_minutes_before=body.reminder_minutes_before,
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
