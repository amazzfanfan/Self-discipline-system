from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.time import local_today
from app.models.behavior import DailyCheckIn
from app.models.user import User
from app.models.task import DifficultyEnum, Task, TaskStatusEnum
from app.schemas.behavior import CheckInRequest, WeeklyPlanRequest
from app.services.behavior_service import (
    build_weekly_review,
    calculate_behavior_metrics,
    last_completed_week_start,
)
from app.services.cache_service import invalidate_tasks
from app.services.task_state_service import maintain_task_states

router = APIRouter(prefix="/api/behavior", tags=["behavior"])


def _checkin_payload(item: DailyCheckIn) -> dict:
    return {
        "id": str(item.id),
        "date": item.checkin_date.isoformat(),
        "sleep_hours": float(item.sleep_hours) if item.sleep_hours is not None else None,
        "energy": item.energy,
        "mood": item.mood,
        "stress": item.stress,
        "available_minutes": item.available_minutes,
        "note": item.note,
    }


@router.get("/checkin/today")
async def get_today_checkin(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    result = await db.execute(
        select(DailyCheckIn).where(DailyCheckIn.user_id == user.id, DailyCheckIn.checkin_date == local_today())
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "今天还没有完成 Check-in")
    return _checkin_payload(item)


@router.put("/checkin/today")
async def upsert_today_checkin(
    body: CheckInRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(DailyCheckIn).where(DailyCheckIn.user_id == user.id, DailyCheckIn.checkin_date == local_today())
    )
    item = result.scalar_one_or_none()
    values = body.model_dump()
    if item:
        for key, value in values.items():
            setattr(item, key, value)
    else:
        item = DailyCheckIn(user_id=user.id, checkin_date=local_today(), **values)
        db.add(item)
    pending_result = await db.execute(
        select(Task).where(
            Task.user_id == user.id,
            Task.scheduled_date == local_today(),
            Task.status == TaskStatusEnum.pending,
        ).order_by(Task.created_at)
    )
    pending_tasks = pending_result.scalars().all()
    configured_budget = int(user.profile.daily_task_budget if user.profile else 3)
    if body.available_minutes <= 20:
        desired_budget = 1
    elif body.available_minutes <= 45:
        desired_budget = min(2, configured_budget)
    else:
        desired_budget = configured_budget
    for task in pending_tasks[desired_budget:]:
        task.status = TaskStatusEnum.deferred
        task.disposition = "excused"
        task.disposition_reason = "根据今日可用时间自动免除"
        task.deferred_until = None
        task.defer_count = (task.defer_count or 0) + 1
        task.rationale = "根据今日可用时间自动免除，不计入行为完成率"
    if body.energy <= 2:
        for task in pending_tasks[:desired_budget]:
            task.difficulty = DifficultyEnum.easy
            task.estimated_minutes = "10-20"
            task.rationale = "根据今日低精力状态自动降低难度"
    await db.flush()
    await invalidate_tasks(str(user.id))
    return _checkin_payload(item)


@router.get("/metrics")
async def get_behavior_metrics(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    await maintain_task_states(db, user.id)
    return await calculate_behavior_metrics(db, user.id)


@router.get("/weekly-review")
async def get_weekly_review(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    await maintain_task_states(db, user.id)
    review = await build_weekly_review(db, user.id, last_completed_week_start())
    return {
        "id": str(review.id),
        "week_start": review.week_start.isoformat(),
        "summary": review.summary,
        "next_week_plan": review.next_week_plan,
        "confirmed": review.confirmed,
    }


@router.put("/weekly-review/plan")
async def confirm_weekly_plan(
    body: WeeklyPlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    review = await build_weekly_review(db, user.id, last_completed_week_start())
    review.next_week_plan = body.model_dump()
    review.confirmed = True
    if user.profile:
        user.profile.daily_task_budget = body.task_budget
    await db.flush()
    effective_week_start = review.week_start + timedelta(days=7)
    return {
        "message": "本周计划已确认",
        "review_week_start": review.week_start.isoformat(),
        "effective_week_start": effective_week_start.isoformat(),
    }
