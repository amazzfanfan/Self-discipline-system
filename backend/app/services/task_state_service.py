from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import app_timezone, local_now, local_today
from app.models.task import Task, TaskStatusEnum
from app.services.notification_service import create_notification
from app.services.score_service import record_negative


TaskScheduleMode = Literal["later", "reschedule", "excuse"]


def _aware_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=app_timezone())
    return value.astimezone(app_timezone())


async def maintain_task_states(db: AsyncSession, user_id=None) -> set[str]:
    """Finalize stale tasks and wake same-day snoozes that have become due."""
    query = select(Task).where(
        or_(
            Task.status.in_([TaskStatusEnum.pending, TaskStatusEnum.in_progress]),
            and_(Task.status == TaskStatusEnum.deferred, Task.disposition == "snoozed"),
        )
    )
    if user_id is not None:
        query = query.where(Task.user_id == user_id)

    result = await db.execute(query)
    now = local_now()
    today = now.date()
    changed_users: set[str] = set()

    for task in result.scalars().all():
        changed = False
        if (
            task.status == TaskStatusEnum.deferred
            and task.disposition == "snoozed"
            and task.deferred_until is not None
            and _aware_local(task.deferred_until) <= now
        ):
            task.deferred_until = None
            if task.scheduled_date < today:
                task.status = TaskStatusEnum.failed
                task.disposition = "expired"
                task.disposition_reason = "稍后提醒到期时已跨日，任务自动结算为未完成"
                await record_negative(
                    db,
                    task.user_id,
                    task.dimension,
                    f"任务过期：{task.title}",
                    task.scheduled_date,
                )
            else:
                task.status = TaskStatusEnum.pending
                task.disposition = None
                task.disposition_reason = None
                await create_notification(
                    db,
                    user_id=task.user_id,
                    kind="task_reminder",
                    title="任务提醒时间到了",
                    message=task.title,
                    dedupe_key=f"task-wakeup:{task.id}:{task.defer_count or 0}",
                    payload={
                        "task_id": str(task.id),
                        "dimension": (
                            task.dimension.value
                            if hasattr(task.dimension, "value")
                            else str(task.dimension)
                        ),
                        "link": "/tasks",
                    },
                    setting_key="task_reminders",
                )
            changed = True
        elif (
            task.status in {TaskStatusEnum.pending, TaskStatusEnum.in_progress}
            and task.scheduled_date < today
        ):
            task.status = TaskStatusEnum.failed
            task.disposition = "expired"
            task.disposition_reason = "任务到期时仍未完成"
            await record_negative(
                db,
                task.user_id,
                task.dimension,
                f"任务过期：{task.title}",
                task.scheduled_date,
            )
            changed = True

        if changed:
            changed_users.add(str(task.user_id))

    return changed_users


async def apply_task_schedule(
    db: AsyncSession,
    task: Task,
    *,
    mode: TaskScheduleMode,
    deferred_until: datetime | None = None,
    target_date: date | None = None,
    reason: str | None = None,
) -> dict:
    """Apply a user-selected schedule outcome to an unfinished task."""
    if task.status not in {
        TaskStatusEnum.pending,
        TaskStatusEnum.in_progress,
        TaskStatusEnum.deferred,
    }:
        return {"success": False, "code": "not_actionable", "message": "该任务已结算，不能再调整"}

    today = local_today()
    clean_reason = reason.strip()[:200] if reason and reason.strip() else None

    if mode == "later":
        if deferred_until is None:
            return {"success": False, "code": "missing_time", "message": "请说明希望稍后几点提醒"}
        wake_at = _aware_local(deferred_until)
        if wake_at <= local_now():
            return {"success": False, "code": "past_time", "message": "提醒时间必须晚于当前时间"}
        if wake_at.date() != today or task.scheduled_date != today:
            return {
                "success": False,
                "code": "cross_day_snooze",
                "message": "跨日安排请使用“改期”，稍后提醒仅限今天",
            }
        task.status = TaskStatusEnum.deferred
        task.disposition = "snoozed"
        task.disposition_reason = clean_reason
        task.deferred_until = wake_at
        task.defer_count = (task.defer_count or 0) + 1
        return {
            "success": True,
            "message": f"已稍后提醒：{task.title}",
            "task_title": task.title,
            "status": task.status.value,
            "disposition": task.disposition,
            "deferred_until": wake_at.isoformat(),
        }

    if mode == "excuse":
        if task.scheduled_date != today:
            return {"success": False, "code": "not_today", "message": "只有今日任务可以设为今日免做"}
        task.status = TaskStatusEnum.deferred
        task.disposition = "excused"
        task.disposition_reason = clean_reason or "用户选择今日免做"
        task.deferred_until = None
        task.defer_count = (task.defer_count or 0) + 1
        return {
            "success": True,
            "message": f"今日已免做：{task.title}",
            "task_title": task.title,
            "status": task.status.value,
            "disposition": task.disposition,
        }

    if target_date is None:
        return {"success": False, "code": "missing_date", "message": "请选择改期日期"}
    if target_date <= today:
        return {"success": False, "code": "invalid_date", "message": "改期日期必须晚于今天"}

    conflict_result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == task.user_id,
                Task.dimension == task.dimension,
                Task.scheduled_date == target_date,
                Task.id != task.id,
            )
        )
    )
    if conflict_result.scalars().first():
        return {
            "success": False,
            "code": "date_conflict",
            "message": "目标日期已有同维度任务，请选择其他日期",
        }

    if task.original_scheduled_date is None:
        task.original_scheduled_date = task.scheduled_date
    task.scheduled_date = target_date
    task.status = TaskStatusEnum.pending
    task.disposition = "rescheduled"
    task.disposition_reason = clean_reason
    task.deferred_until = None
    task.defer_count = (task.defer_count or 0) + 1
    return {
        "success": True,
        "message": f"任务已改期至 {target_date.isoformat()}：{task.title}",
        "task_title": task.title,
        "status": task.status.value,
        "disposition": task.disposition,
        "scheduled_date": target_date.isoformat(),
    }
