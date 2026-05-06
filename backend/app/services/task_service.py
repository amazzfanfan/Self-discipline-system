from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.task import Task, TaskStatusEnum
from app.models.score import DimensionEnum
from app.services.score_service import record_task_completion, record_negative


async def complete_task_by_dimension(db: AsyncSession, user_id: str, dimension: str) -> dict:
    """Complete today's pending task for a dimension. Returns result dict."""
    dim_enum = DimensionEnum(dimension)
    result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.scheduled_date == date.today(),
                Task.dimension == dim_enum,
                Task.status == TaskStatusEnum.pending,
            )
        )
    )
    task = result.scalars().first()
    if not task:
        return {"success": False, "message": "该维度今日无待完成任务"}

    task.status = TaskStatusEnum.completed
    task.completed_at = datetime.now(timezone.utc)

    score_change = await record_task_completion(db, user_id, dim_enum)
    return {
        "success": True,
        "message": f"任务已完成：{task.title}",
        "task_title": task.title,
        "score_change": score_change,
    }


async def skip_task_by_dimension(db: AsyncSession, user_id: str, dimension: str) -> dict:
    """Mark today's pending task for a dimension as failed. Returns result dict."""
    dim_enum = DimensionEnum(dimension)
    result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.scheduled_date == date.today(),
                Task.dimension == dim_enum,
                Task.status == TaskStatusEnum.pending,
            )
        )
    )
    task = result.scalars().first()
    if not task:
        return {"success": False, "message": "该维度今日无待完成任务"}

    task.status = TaskStatusEnum.failed

    score_change = await record_negative(db, user_id, dim_enum, f"跳过任务：{task.title}")
    return {
        "success": True,
        "message": f"已跳过任务：{task.title}",
        "task_title": task.title,
        "score_change": score_change,
    }


async def get_today_tasks_dict(db: AsyncSession, user_id: str) -> list[dict]:
    """Get today's tasks as list of dicts for intent detection."""
    result = await db.execute(
        select(Task).where(
            and_(Task.user_id == user_id, Task.scheduled_date == date.today())
        )
    )
    return [
        {"dimension": t.dimension.value, "title": t.title, "status": t.status.value}
        for t in result.scalars().all()
    ]
