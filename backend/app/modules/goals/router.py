"""
Goals Router - 目标管理 API
提供目标的创建、查询、更新、删除和搜索功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.goal_service import goal_service

router = APIRouter(prefix="/api/goals", tags=["goals"])


# ── Pydantic 请求/响应模型 ──────────────────────────────────────────

class GoalCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, description="目标内容")
    goal_type: str = Field(default="exercise", description="目标类型: exercise/diet/sleep/appearance")
    structured_data: Optional[dict] = Field(default=None, description="结构化数据")
    target_metric: Optional[str] = Field(default=None, max_length=100)
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    deadline: Optional[date] = None
    milestones: list[dict] = Field(default_factory=list, max_length=20)


class GoalUpdateRequest(BaseModel):
    content: Optional[str] = Field(default=None, max_length=2000, description="目标内容")
    goal_type: Optional[str] = Field(default=None, description="目标类型")
    status: Optional[str] = Field(default=None, description="目标状态: active/completed/paused")
    importance_score: Optional[float] = Field(default=None, ge=0, le=1, description="重要性评分")
    structured_data: Optional[dict] = Field(default=None, description="结构化数据")
    target_metric: Optional[str] = Field(default=None, max_length=100)
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    deadline: Optional[date] = None
    milestones: Optional[list[dict]] = Field(default=None, max_length=20)


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
        source="manual",
    )
    return goal.to_dict()


@router.get("")
async def list_goals(
    status: Optional[str] = Query(default=None, description="按状态过滤"),
    goal_type: Optional[str] = Query(default=None, description="按类型过滤"),
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
    status: Optional[str] = Query(default=None, description="按状态过滤"),
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
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

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
