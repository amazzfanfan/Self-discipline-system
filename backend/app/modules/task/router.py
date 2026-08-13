from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.user import UserProfile
from app.models.task import Task, TaskEvent, TaskStatusEnum
from app.models.assessment import AssessmentRun
from app.models.goal import Goal
from app.models.score import UserScore
from app.services.cache_service import get_cached_tasks, set_cached_tasks, invalidate_tasks, invalidate_scores
from app.core.time import local_today
from app.services.task_state_service import apply_task_schedule, maintain_task_states
from app.services.task_event_service import record_task_event
from app.services.goal_progress_service import (
    record_goal_task_completion,
    revert_goal_task_completion,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

DIMENSION_NAMES = {
    "exercise": "运动状态",
    "diet": "饮食习惯",
    "sleep": "睡眠状态",
    "appearance": "形象管理",
}


class TaskFeedbackRequest(BaseModel):
    feedback: Literal["too_easy", "just_right", "too_hard", "not_suitable"]


class TaskScheduleRequest(BaseModel):
    mode: Literal["later", "reschedule", "excuse"]
    deferred_until: datetime | None = None
    target_date: date | None = None
    reason: str | None = None


def _task_why(
    task: Task,
    *,
    scores_by_dimension: dict | None = None,
    goals_by_id: dict | None = None,
    skin_analysis: dict | None = None,
) -> list[str]:
    """Human-readable reasons for this task, separate from adaptation mechanics."""
    why: list[str] = []
    dimension = task.dimension.value
    scores_by_dimension = scores_by_dimension or {}
    goals_by_id = goals_by_id or {}

    goal = goals_by_id.get(str(getattr(task, "goal_id", "") or ""))
    if goal:
        why.append(f"为了推进你的成长目标：{str(goal.content)[:60]}")
    else:
        score = scores_by_dimension.get(task.dimension)
        if score is not None:
            baseline = float(score.baseline_score)
            all_baselines = [float(item.baseline_score) for item in scores_by_dimension.values()]
            lowest = min(all_baselines) if all_baselines else baseline
            name = DIMENSION_NAMES.get(dimension, dimension)
            if baseline <= lowest + 5:
                why.append(f"你的{name}基线为 {baseline:.0f} 分，是当前优先关注的方向")
            else:
                why.append(f"为了维持你的{name}，安排一项今天可以完成的小行动")

    if dimension == "appearance" and isinstance(skin_analysis, dict):
        issues = [str(item) for item in (skin_analysis.get("issues") or []) if item]
        if skin_analysis.get("source") == "faceplusplus" and issues:
            why.append(f"Face++ 观察到{ '、'.join(issues[:3]) }，所以这项任务优先围绕这些日常护理点")

    metadata = getattr(task, "adaptation_metadata", None) or {}
    reasons = metadata.get("reasons") if isinstance(metadata, dict) else None
    if isinstance(reasons, list) and reasons:
        why.append(f"今天的时长和难度已根据{ '、'.join(str(item) for item in reasons[:2]) }调整")
    elif isinstance(metadata, dict) and metadata.get("version"):
        signals = metadata.get("signals") or {}
        if int(signals.get("history_count", 0) or 0) == 0:
            why.append("你还没有足够的近期执行记录，系统先用中等难度建立基线，再根据你的反馈调整")

    return why[:3]


def _task_payload(task: Task, *, why: list[str] | None = None) -> dict:
    return {
        "id": str(task.id),
        "goal_id": (
            str(task.goal_id) if getattr(task, "goal_id", None) else None
        ),
        "dimension": task.dimension.value,
        "title": task.title,
        "description": task.description,
        "difficulty": task.difficulty.value,
        "scheduled_date": task.scheduled_date.isoformat(),
        "scheduled_time": (
            task.scheduled_time.strftime("%H:%M")
            if getattr(task, "scheduled_time", None)
            else None
        ),
        "source": getattr(task, "source", "adaptive"),
        "status": task.status.value,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "rationale": task.rationale,
        "estimated_minutes": task.estimated_minutes,
        "user_feedback": task.user_feedback,
        "disposition": getattr(task, "disposition", None),
        "disposition_reason": getattr(task, "disposition_reason", None),
        "deferred_until": (
            task.deferred_until.isoformat() if getattr(task, "deferred_until", None) else None
        ),
        "defer_count": getattr(task, "defer_count", 0) or 0,
        "original_scheduled_date": (
            task.original_scheduled_date.isoformat()
            if getattr(task, "original_scheduled_date", None)
            else None
        ),
        "adaptation_metadata": getattr(task, "adaptation_metadata", None) or {},
        "why": why or [],
    }


async def _task_context(db: AsyncSession, user_id) -> tuple[dict, dict, dict | None]:
    scores = {
        item.dimension: item
        for item in (await db.execute(select(UserScore).where(UserScore.user_id == user_id))).scalars().all()
    }
    goals = {
        str(item.id): item
        for item in (await db.execute(select(Goal).where(Goal.user_id == user_id))).scalars().all()
    }
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    skin_analysis = profile.skin_analysis if profile and isinstance(profile.skin_analysis, dict) else None
    return scores, goals, skin_analysis


def _task_payloads(tasks: list[Task], context: tuple[dict, dict, dict | None]) -> list[dict]:
    scores, goals, skin_analysis = context
    return [
        _task_payload(
            task,
            why=_task_why(
                task,
                scores_by_dimension=scores,
                goals_by_id=goals,
                skin_analysis=skin_analysis,
            ),
        )
        for task in tasks
    ]


@router.get("/today")
async def get_today_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    changed_users = await maintain_task_states(db, user.id)
    if str(user.id) in changed_users:
        await invalidate_tasks(str(user.id))
    # 先查缓存
    cached = await get_cached_tasks(str(user.id))
    if cached is not None and all("why" in task for task in cached):
        return cached

    result = await db.execute(
        select(Task).where(and_(Task.user_id == user.id, Task.scheduled_date == local_today()))
    )
    tasks = result.scalars().all()

    # 如果今天没有任务（定时器可能没触发），自动生成
    if not tasks:
        generation_status = await db.scalar(
            select(AssessmentRun.generation_status)
            .where(AssessmentRun.user_id == user.id)
            .order_by(AssessmentRun.created_at.desc())
            .limit(1)
        )
        if generation_status in {"pending", "running"}:
            return []
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

    result_list = _task_payloads(tasks, await _task_context(db, user.id))

    # 写入缓存
    await set_cached_tasks(str(user.id), result_list)
    return result_list


@router.post("/{task_id}/complete")
async def complete_task(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    result = await db.execute(
        select(Task)
        .where(and_(Task.id == task_id, Task.user_id == user.id))
        .with_for_update()
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in {TaskStatusEnum.pending, TaskStatusEnum.in_progress, TaskStatusEnum.deferred}:
        raise HTTPException(409, "Task is no longer completable")

    previous_status = task.status
    task.status = TaskStatusEnum.completed
    task.completed_at = datetime.now(timezone.utc)
    task.disposition = None
    task.disposition_reason = None
    task.deferred_until = None

    from app.services.score_service import record_task_completion
    score_change = await record_task_completion(db, user.id, task.dimension, task.scheduled_date)
    goal_progress = await record_goal_task_completion(db, task)
    await record_task_event(
        db,
        task,
        "completed",
        actor="user",
        source="api",
        from_status=previous_status,
        to_status=task.status,
    )

    # 清除缓存
    await invalidate_tasks(str(user.id))
    await invalidate_scores(str(user.id))

    return {
        "message": "任务完成",
        "score_change": score_change,
        "goal_progress": goal_progress,
    }


@router.post("/{task_id}/feedback")
async def save_task_feedback(
    task_id: str,
    body: TaskFeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(Task)
        .where(and_(Task.id == task_id, Task.user_id == user.id))
        .with_for_update()
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    task.user_feedback = body.feedback
    await record_task_event(
        db,
        task,
        "feedback_recorded",
        actor="user",
        source="api",
        metadata={"feedback": body.feedback},
    )
    return {"message": "反馈已记录", "feedback": body.feedback}


@router.post("/{task_id}/reopen")
async def reopen_completed_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(Task)
        .where(and_(Task.id == task_id, Task.user_id == user.id))
        .with_for_update()
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatusEnum.completed:
        raise HTTPException(409, "Only completed tasks can be reopened")
    if task.scheduled_date != local_today():
        raise HTTPException(409, "Only today's completion can be corrected")

    previous_status = task.status
    task.status = TaskStatusEnum.pending
    task.completed_at = None
    goal_progress = await revert_goal_task_completion(db, task)
    from app.services.score_service import rebuild_behavior_counters

    behavior = await rebuild_behavior_counters(db, user.id, task.dimension)
    await record_task_event(
        db,
        task,
        "completion_reverted",
        actor="user",
        source="api",
        reason="用户撤销了误标的完成记录",
        from_status=previous_status,
        to_status=task.status,
    )
    await invalidate_tasks(str(user.id))
    await invalidate_scores(str(user.id))
    return {
        "message": "完成记录已撤销，任务恢复为待完成",
        "goal_progress": goal_progress,
        "behavior": behavior,
    }


@router.post("/{task_id}/defer")
async def defer_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(Task)
        .where(and_(Task.id == task_id, Task.user_id == user.id))
        .with_for_update()
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    scheduled = await apply_task_schedule(db, task, mode="excuse")
    if not scheduled["success"]:
        raise HTTPException(409, scheduled["message"])
    await invalidate_tasks(str(user.id))
    return scheduled


@router.post("/{task_id}/schedule")
async def schedule_task(
    task_id: str,
    body: TaskScheduleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(Task)
        .where(and_(Task.id == task_id, Task.user_id == user.id))
        .with_for_update()
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    scheduled = await apply_task_schedule(
        db,
        task,
        mode=body.mode,
        deferred_until=body.deferred_until,
        target_date=body.target_date,
        reason=body.reason,
    )
    if not scheduled["success"]:
        raise HTTPException(409, scheduled["message"])
    await invalidate_tasks(str(user.id))
    return scheduled


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(Task)
        .where(and_(Task.id == task_id, Task.user_id == user.id))
        .with_for_update()
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatusEnum.deferred:
        raise HTTPException(409, "Only deferred tasks can be resumed")
    if task.scheduled_date != local_today():
        raise HTTPException(409, "Only today's deferred task can be resumed")
    previous_status = task.status
    task.status = TaskStatusEnum.pending
    task.disposition = None
    task.disposition_reason = None
    task.deferred_until = None
    await record_task_event(
        db,
        task,
        "resumed",
        actor="user",
        source="api",
        from_status=previous_status,
        to_status=task.status,
    )
    await invalidate_tasks(str(user.id))
    return {"message": "任务已恢复为待完成"}


@router.get("/{task_id}/events")
async def get_task_events(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    task = await db.scalar(
        select(Task).where(and_(Task.id == task_id, Task.user_id == user.id))
    )
    if not task:
        raise HTTPException(404, "Task not found")
    events = (
        await db.execute(
            select(TaskEvent)
            .where(TaskEvent.task_id == task.id)
            .order_by(TaskEvent.created_at.asc())
        )
    ).scalars().all()
    return [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "reason": event.reason,
            "actor": event.actor,
            "source": event.source,
            "metadata": event.event_metadata or {},
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]


@router.get("")
async def list_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
    dimension: Literal["exercise", "diet", "sleep", "appearance"] | None = None,
    status: Literal["pending", "in_progress", "completed", "failed", "deferred"] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    changed_users = await maintain_task_states(db, user.id)
    if str(user.id) in changed_users:
        await invalidate_tasks(str(user.id))
    query = select(Task).where(Task.user_id == user.id)
    if dimension:
        query = query.where(Task.dimension == dimension)
    if status:
        query = query.where(Task.status == status)
    if start_date:
        query = query.where(Task.scheduled_date >= start_date)
    if end_date:
        query = query.where(Task.scheduled_date <= end_date)
    if start_date and end_date and end_date < start_date:
        raise HTTPException(422, "end_date must not be before start_date")
    query = query.order_by(Task.scheduled_date.desc()).limit(limit)

    result = await db.execute(query)
    tasks = result.scalars().all()
    return _task_payloads(tasks, await _task_context(db, user.id))
