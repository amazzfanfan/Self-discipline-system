from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.task import Task, TaskStatusEnum
from app.models.score import DimensionEnum
from app.services.score_service import record_task_completion, record_negative
from app.core.time import local_today
from app.services.task_state_service import apply_task_schedule, maintain_task_states


async def complete_task_by_dimension(db: AsyncSession, user_id: str, dimension: str) -> dict:
    """Complete today's pending task for a dimension. Returns result dict."""
    dim_enum = DimensionEnum(dimension)
    result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.scheduled_date == local_today(),
                Task.dimension == dim_enum,
                Task.status.in_([
                    TaskStatusEnum.pending,
                    TaskStatusEnum.in_progress,
                    TaskStatusEnum.deferred,
                ]),
            )
        )
    )
    task = result.scalars().first()
    if not task:
        return {"success": False, "message": "该维度今日无待完成任务"}

    task.status = TaskStatusEnum.completed
    task.completed_at = datetime.now(timezone.utc)
    task.disposition = None
    task.disposition_reason = None
    task.deferred_until = None

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
                Task.scheduled_date == local_today(),
                Task.dimension == dim_enum,
                Task.status.in_([
                    TaskStatusEnum.pending,
                    TaskStatusEnum.in_progress,
                    TaskStatusEnum.deferred,
                ]),
            )
        )
    )
    task = result.scalars().first()
    if not task:
        return {"success": False, "message": "该维度今日无待完成任务"}

    task.status = TaskStatusEnum.failed
    task.disposition = "skipped"
    task.disposition_reason = "用户明确跳过任务"
    task.deferred_until = None

    score_change = await record_negative(db, user_id, dim_enum, f"跳过任务：{task.title}")
    return {
        "success": True,
        "message": f"已跳过任务：{task.title}",
        "task_title": task.title,
        "score_change": score_change,
    }


async def replace_task_by_dimension(
    db: AsyncSession,
    user_id: str,
    dimension: str,
    title: str,
    reason: str | None = None,
) -> dict:
    """Replace today's unfinished task and return an auditable before/after result."""
    dim_enum = DimensionEnum(dimension)
    result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.scheduled_date == local_today(),
                Task.dimension == dim_enum,
                Task.status.in_([
                    TaskStatusEnum.pending,
                    TaskStatusEnum.in_progress,
                    TaskStatusEnum.deferred,
                ]),
            )
        )
    )
    task = result.scalars().first()
    if not task:
        return {"success": False, "message": "该维度今日没有可修改的未完成任务"}

    old_title = task.title
    task.title = title.strip()[:200]
    task.description = ""
    task.rationale = (reason or "用户通过对话调整了今日任务")[:500]
    task.source = "chat_modified"
    task.adaptation_metadata = {
        "version": "manual",
        "reasons": [reason or "用户通过对话明确修改任务"],
    }
    task.status = TaskStatusEnum.pending
    task.disposition = None
    task.disposition_reason = None
    task.deferred_until = None
    return {
        "success": True,
        "message": f"任务已更新：{task.title}",
        "dimension": dimension,
        "old_title": old_title,
        "new_title": task.title,
    }


async def defer_task_by_dimension(
    db: AsyncSession,
    user_id: str,
    dimension: str,
    *,
    mode: str,
    deferred_until: datetime | None = None,
    target_date: date | None = None,
    reason: str | None = None,
) -> dict:
    """Snooze, reschedule, or excuse today's task for a dimension."""
    dim_enum = DimensionEnum(dimension)
    result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.scheduled_date == local_today(),
                Task.dimension == dim_enum,
                Task.status.in_([
                    TaskStatusEnum.pending,
                    TaskStatusEnum.in_progress,
                    TaskStatusEnum.deferred,
                ]),
            )
        )
    )
    task = result.scalars().first()
    if not task:
        return {"success": False, "message": "该维度今日没有可调整的任务"}
    return await apply_task_schedule(
        db,
        task,
        mode=mode,
        deferred_until=deferred_until,
        target_date=target_date,
        reason=reason,
    )


async def resume_task_by_dimension(db: AsyncSession, user_id: str, dimension: str) -> dict:
    """Return a deferred task to today's actionable queue."""
    dim_enum = DimensionEnum(dimension)
    result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.scheduled_date == local_today(),
                Task.dimension == dim_enum,
                Task.status == TaskStatusEnum.deferred,
            )
        )
    )
    task = result.scalars().first()
    if not task:
        return {"success": False, "message": "该维度今日没有已暂缓任务"}
    task.status = TaskStatusEnum.pending
    task.disposition = None
    task.disposition_reason = None
    task.deferred_until = None
    return {
        "success": True,
        "message": f"任务已恢复为待完成：{task.title}",
        "task_title": task.title,
        "status": "pending",
    }


async def get_today_tasks_dict(db: AsyncSession, user_id: str) -> list[dict]:
    """Get today's tasks as list of dicts for intent detection."""
    await maintain_task_states(db, user_id)
    result = await db.execute(
        select(Task).where(
            and_(Task.user_id == user_id, Task.scheduled_date == local_today())
        )
    )
    return [
        {
            "dimension": t.dimension.value,
            "title": t.title,
            "status": t.status.value,
            "disposition": t.disposition,
            "deferred_until": t.deferred_until.isoformat() if t.deferred_until else None,
        }
        for t in result.scalars().all()
    ]
