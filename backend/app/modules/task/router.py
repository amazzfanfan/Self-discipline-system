from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.task import Task, TaskStatusEnum
from app.services.cache_service import get_cached_tasks, set_cached_tasks, invalidate_tasks, invalidate_scores
from app.core.time import local_today

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskFeedbackRequest(BaseModel):
    feedback: Literal["too_easy", "just_right", "too_hard", "not_suitable"]


def _task_payload(task: Task) -> dict:
    return {
        "id": str(task.id),
        "dimension": task.dimension.value,
        "title": task.title,
        "description": task.description,
        "difficulty": task.difficulty.value,
        "scheduled_date": task.scheduled_date.isoformat(),
        "status": task.status.value,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "rationale": task.rationale,
        "estimated_minutes": task.estimated_minutes,
        "user_feedback": task.user_feedback,
    }


@router.get("/today")
async def get_today_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    # 先查缓存
    cached = await get_cached_tasks(str(user.id))
    if cached is not None:
        return cached

    result = await db.execute(
        select(Task).where(and_(Task.user_id == user.id, Task.scheduled_date == local_today()))
    )
    tasks = result.scalars().all()

    # 如果今天没有任务（定时器可能没触发），自动生成
    if not tasks:
        from app.services.scheduler_service import generate_tasks_for_user
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"今日无任务，为用户 {user.id} 自动生成")
        try:
            await generate_tasks_for_user(user.id, user.nickname, db)
            await db.commit()
            # 重新查询
            result = await db.execute(
                select(Task).where(and_(Task.user_id == user.id, Task.scheduled_date == local_today()))
            )
            tasks = result.scalars().all()
        except Exception as e:
            await db.rollback()
            logger.error(f"自动生成任务失败: {e}")
            raise HTTPException(
                503,
                "AI 今日任务生成暂时失败，请稍后重试。",
            ) from e

    result_list = [_task_payload(task) for task in tasks]

    # 写入缓存
    await set_cached_tasks(str(user.id), result_list)
    return result_list


@router.post("/{task_id}/complete")
async def complete_task(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    result = await db.execute(select(Task).where(and_(Task.id == task_id, Task.user_id == user.id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in {TaskStatusEnum.pending, TaskStatusEnum.in_progress, TaskStatusEnum.deferred}:
        raise HTTPException(409, "Task is no longer completable")

    from datetime import datetime, timezone
    task.status = TaskStatusEnum.completed
    task.completed_at = datetime.now(timezone.utc)

    from app.services.score_service import record_task_completion
    score_change = await record_task_completion(db, user.id, task.dimension)

    # 清除缓存
    await invalidate_tasks(str(user.id))
    await invalidate_scores(str(user.id))

    return {
        "message": "任务完成",
        "score_change": score_change,
    }


@router.post("/{task_id}/feedback")
async def save_task_feedback(
    task_id: str,
    body: TaskFeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(select(Task).where(and_(Task.id == task_id, Task.user_id == user.id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    task.user_feedback = body.feedback
    return {"message": "反馈已记录", "feedback": body.feedback}


@router.post("/{task_id}/defer")
async def defer_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(select(Task).where(and_(Task.id == task_id, Task.user_id == user.id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in {TaskStatusEnum.pending, TaskStatusEnum.in_progress}:
        raise HTTPException(409, "Task cannot be deferred")
    task.status = TaskStatusEnum.deferred
    await invalidate_tasks(str(user.id))
    return {
        "message": "任务已设为今日暂缓；不算完成或跳过、不扣分，也不会自动移到明天，可随时恢复"
    }


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(select(Task).where(and_(Task.id == task_id, Task.user_id == user.id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatusEnum.deferred:
        raise HTTPException(409, "Only deferred tasks can be resumed")
    task.status = TaskStatusEnum.pending
    await invalidate_tasks(str(user.id))
    return {"message": "任务已恢复为待完成"}


@router.get("")
async def list_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
    dimension: Literal["exercise", "diet", "sleep", "appearance"] | None = None,
    status: Literal["pending", "in_progress", "completed", "failed", "deferred"] | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    query = select(Task).where(Task.user_id == user.id)
    if dimension:
        query = query.where(Task.dimension == dimension)
    if status:
        query = query.where(Task.status == status)
    query = query.order_by(Task.scheduled_date.desc()).limit(limit)

    result = await db.execute(query)
    return [_task_payload(task) for task in result.scalars().all()]
