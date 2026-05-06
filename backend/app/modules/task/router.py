from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.task import Task, TaskStatusEnum
from app.models.score import DimensionEnum
from app.services.score_service import record_task_completion

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/today")
async def get_today_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(and_(Task.user_id == user.id, Task.scheduled_date == date.today()))
    )
    tasks = result.scalars().all()
    return [
        {
            "id": str(t.id), "dimension": t.dimension.value, "title": t.title,
            "description": t.description, "difficulty": t.difficulty.value,
            "status": t.status.value, "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ]


@router.post("/{task_id}/complete")
async def complete_task(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(and_(Task.id == task_id, Task.user_id == user.id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status == TaskStatusEnum.completed:
        raise HTTPException(400, "Already completed")

    from datetime import datetime, timezone
    task.status = TaskStatusEnum.completed
    task.completed_at = datetime.now(timezone.utc)

    score_change = await record_task_completion(db, user.id, task.dimension)

    return {
        "message": "任务完成",
        "score_change": score_change,
    }


@router.get("")
async def list_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                     dimension: str | None = None, status: str | None = None, limit: int = 20):
    query = select(Task).where(Task.user_id == user.id)
    if dimension:
        query = query.where(Task.dimension == dimension)
    if status:
        query = query.where(Task.status == status)
    query = query.order_by(Task.scheduled_date.desc()).limit(limit)

    result = await db.execute(query)
    return [
        {
            "id": str(t.id), "dimension": t.dimension.value, "title": t.title,
            "scheduled_date": t.scheduled_date.isoformat(), "status": t.status.value,
        }
        for t in result.scalars().all()
    ]
