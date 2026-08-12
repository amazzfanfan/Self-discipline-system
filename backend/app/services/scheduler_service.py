import asyncio
import logging
from datetime import datetime, time as clock_time, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, select
from app.core.config import get_settings
from app.core.database import async_session
from app.core.time import app_timezone, local_now, local_today
from app.models.user import User, UserProfile
from app.models.score import UserScore, DimensionEnum
from app.models.task import Task, TaskEvent, TaskStatusEnum
from app.models.conversation import Conversation, RoleEnum
from app.models.goal import Goal, GoalStatus
from app.models.behavior import DailyCheckIn
from app.services.ai_service import generate_task
from app.services.faceplus_service import generate_skin_task_ai
from app.services.goal_service import goal_service
from app.services.cache_service import acquire_lock, invalidate_tasks, release_lock
from app.services.task_state_service import maintain_task_states
from app.services.notification_service import create_notification
from app.services.task_event_service import record_task_event
from app.services.adaptive_task_service import (
    ADAPTATION_VERSION,
    analyze_history,
    choose_task_budget,
    decide_adaptation,
    dimension_priority,
)
from app.services.behavior_service import last_completed_week_start
from app.services.goal_schedule_service import goal_is_due, goal_planning_context
from app.services.goal_progress_service import build_goal_progress_summaries

settings = get_settings()
logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=settings.APP_TIMEZONE)

TASKS_PER_DIMENSION = {
    DimensionEnum.exercise: 1,
    DimensionEnum.diet: 1,
    DimensionEnum.sleep: 1,
    DimensionEnum.appearance: 1,
}

DIMENSION_LABELS = {
    DimensionEnum.exercise: "运动",
    DimensionEnum.diet: "饮食",
    DimensionEnum.sleep: "睡眠",
    DimensionEnum.appearance: "形象管理",
}


async def generate_tasks_for_user(
    user_id,
    nickname: str,
    db=None,
    *,
    regenerate_pending: bool = False,
):
    """Generate AI-authored tasks concurrently for a single user."""
    async def _generate(session):
        await maintain_task_states(session, user_id)
        today = local_today()
        existing_result = await session.execute(
            select(Task).where(
                and_(Task.user_id == user_id, Task.scheduled_date == today)
            )
        )
        existing_tasks = existing_result.scalars().all()
        existing_by_dimension = {task.dimension: task for task in existing_tasks}
        existing_dimensions = set(existing_by_dimension)
        scores_result = await session.execute(select(UserScore).where(UserScore.user_id == user_id))
        scores = {s.dimension: s for s in scores_result.scalars().all()}

        # 获取用户的肤质分析结果
        profile_result = await session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        skin_analysis = profile.skin_analysis if profile else None

        recent_result = await session.execute(
            select(Task).where(
                Task.user_id == user_id,
                Task.scheduled_date >= today - timedelta(days=14),
                Task.scheduled_date < today,
            ).order_by(Task.scheduled_date.desc())
        )
        recent_tasks = recent_result.scalars().all()
        recent_task_ids = [task.id for task in recent_tasks]
        if recent_task_ids:
            event_result = await session.execute(
                select(TaskEvent).where(TaskEvent.task_id.in_(recent_task_ids))
            )
            recent_events = event_result.scalars().all()
        else:
            recent_events = []
        dimension_by_task_id = {task.id: task.dimension for task in recent_tasks}
        events_by_dimension = {
            dim: [
                event
                for event in recent_events
                if dimension_by_task_id.get(event.task_id) == dim
            ]
            for dim in TASKS_PER_DIMENSION
        }
        checkin_result = await session.execute(
            select(DailyCheckIn).where(
                DailyCheckIn.user_id == user_id,
                DailyCheckIn.checkin_date == today,
            )
        )
        checkin = checkin_result.scalar_one_or_none()

        # 获取用户目标并按类型分组
        goals_by_type = {}
        try:
            user_goals = await goal_service.get_user_goals(
                db=session,
                user_id=user_id,
                status=GoalStatus.active.value
            )
            week_start = today - timedelta(days=today.weekday())
            progress_summaries = await build_goal_progress_summaries(
                session,
                user_id,
                period_start=week_start,
                period_end=week_start + timedelta(days=6),
                as_of=today,
            )
            # 按目标类型分组，每个类型取今天实际需要执行的最新目标。
            for goal in user_goals:
                goal_type = goal.get("goal_type")
                if (
                    goal_type
                    and goal_type not in goals_by_type
                    and goal_is_due(goal, today)
                ):
                    goals_by_type[goal_type] = {
                        **goal,
                        "progress_summary": progress_summaries.get(goal["id"]),
                    }
            print(f"[任务生成] 用户 {user_id} 有 {len(user_goals)} 个活跃目标，覆盖类型: {list(goals_by_type.keys())}")
        except Exception as e:
            print(f"[任务生成] 获取用户目标失败: {e}")

        configured_budget = int(profile.daily_task_budget if profile else 3)
        task_budget = choose_task_budget(configured_budget, checkin)
        history_by_dimension = {
            dim: [task for task in recent_tasks if task.dimension == dim]
            for dim in TASKS_PER_DIMENSION
        }
        signals_by_dimension = {
            dim: analyze_history(
                history_by_dimension[dim],
                events_by_dimension[dim],
            )
            for dim in TASKS_PER_DIMENSION
        }
        ordered_dimensions = sorted(
            TASKS_PER_DIMENSION,
            key=lambda dim: dimension_priority(
                baseline=float(scores[dim].baseline_score) if dim in scores else 100.0,
                has_goal=dim.value in goals_by_type,
                signals=signals_by_dimension[dim],
            ),
            reverse=True,
        )
        target_dimensions = set(ordered_dimensions[:task_budget])
        if not regenerate_pending and target_dimensions.issubset(existing_dimensions):
            for dim in target_dimensions:
                task = existing_by_dimension[dim]
                if (
                    task.status in {TaskStatusEnum.pending, TaskStatusEnum.in_progress}
                    and (task.adaptation_metadata or {}).get("version") != ADAPTATION_VERSION
                ):
                    score_record = scores.get(dim)
                    if not score_record:
                        continue
                    adaptation = decide_adaptation(
                        baseline=float(score_record.baseline_score),
                        signals=signals_by_dimension[dim],
                        checkin=checkin,
                        task_budget=task_budget,
                    )
                    task.difficulty = adaptation.difficulty
                    task.estimated_minutes = adaptation.estimated_minutes
                    task.rationale = adaptation.rationale
                    task.adaptation_metadata = adaptation.metadata
                    goal = goals_by_type.get(dim.value)
                    if goal:
                        task.goal_id = goal["id"]
                        task.scheduled_time = (
                            clock_time.fromisoformat(goal["preferred_time"])
                            if goal.get("preferred_time")
                            else None
                        )
                    await record_task_event(
                        session,
                        task,
                        "adapted",
                        actor="system",
                        source="scheduler",
                        reason=adaptation.rationale,
                        from_status=task.status,
                        to_status=task.status,
                        metadata={"version": ADAPTATION_VERSION},
                    )
            return

        task_specs = []
        for dim in TASKS_PER_DIMENSION:
            if dim not in target_dimensions:
                continue
            existing_task = existing_by_dimension.get(dim)
            if existing_task and not (
                regenerate_pending and existing_task.status == TaskStatusEnum.pending
            ):
                continue
            score_record = scores.get(dim)
            if not score_record:
                continue

            score_val = float(score_record.baseline_score)
            dimension_history = history_by_dimension[dim]
            adaptation = decide_adaptation(
                baseline=score_val,
                signals=signals_by_dimension[dim],
                checkin=checkin,
                task_budget=task_budget,
            )
            difficulty = adaptation.difficulty

            goal = goals_by_type.get(dim.value)
            goal_content = goal_planning_context(goal) if goal else None
            if goal:
                logger.info(
                    "User %s has a %s goal: %s",
                    user_id,
                    dim.value,
                    goal["content"][:50],
                )
            task_specs.append({
                "dimension": dim,
                "difficulty": difficulty,
                "score": score_val,
                "recent_titles": [task.title for task in dimension_history[:6]],
                "goal_content": goal_content,
                "goal": goal,
                "existing_task": existing_task,
                "adaptation": adaptation,
            })

        async def _generate_title(spec: dict) -> str:
            dimension = spec["dimension"]
            if (
                dimension == DimensionEnum.appearance
                and not spec["goal"]
                and isinstance(skin_analysis, dict)
                and skin_analysis.get("source") == "faceplusplus"
            ):
                return await _generate_skin_based_task(skin_analysis)
            adaptation = spec["adaptation"]
            signals = adaptation.metadata["signals"]
            adaptation_notes = (
                f"自适应要求：任务预计 {adaptation.estimated_minutes} 分钟；"
                f"{adaptation.rationale}。"
            )
            if signals.get("not_suitable", 0) > 0:
                adaptation_notes += "用户曾反馈任务不适合，必须更换行动形式，不能只改数字。"
            elif signals.get("too_hard", 0) > 0:
                adaptation_notes += "用户曾反馈太难，应减少步骤、强度或准备成本。"
            elif signals.get("too_easy", 0) > 0:
                adaptation_notes += "用户曾反馈太简单，应增加一个可量化挑战。"
            return await generate_task(
                nickname=nickname,
                dimension=dimension.value,
                score=spec["score"],
                difficulty=spec["difficulty"].value,
                recent_tasks=spec["recent_titles"],
                goal_content=spec["goal_content"],
                adaptation_context=adaptation_notes,
            )

        # These calls are independent. Running them concurrently avoids making
        # onboarding latency grow linearly with the number of selected dimensions.
        task_titles = await asyncio.gather(
            *(_generate_title(spec) for spec in task_specs)
        )

        generated_tasks = []
        for spec, generated_title in zip(task_specs, task_titles, strict=True):
            dim = spec["dimension"]
            difficulty = spec["difficulty"]
            adaptation = spec["adaptation"]
            task_title = generated_title[:200]
            rationale = adaptation.rationale
            estimated_minutes = adaptation.estimated_minutes
            task = spec["existing_task"]
            goal = spec["goal"]
            scheduled_time = (
                clock_time.fromisoformat(goal["preferred_time"])
                if goal and goal.get("preferred_time")
                else None
            )
            if task:
                previous_title = task.title
                task.title = task_title
                task.rationale = rationale
                task.estimated_minutes = estimated_minutes
                task.difficulty = difficulty
                task.adaptation_metadata = adaptation.metadata
                task.goal_id = goal["id"] if goal else None
                task.scheduled_time = scheduled_time
                task.source = "goal" if goal else "adaptive"
                await record_task_event(
                    session,
                    task,
                    "regenerated",
                    actor="system",
                    source="scheduler",
                    reason=rationale,
                    from_status=task.status,
                    to_status=task.status,
                    metadata={
                        "old_title": previous_title,
                        "new_title": task_title,
                        "version": ADAPTATION_VERSION,
                        "goal_id": goal["id"] if goal else None,
                    },
                )
            else:
                task = Task(
                    user_id=user_id,
                    dimension=dim,
                    title=task_title,
                    description="",
                    rationale=rationale,
                    estimated_minutes=estimated_minutes,
                    difficulty=difficulty,
                    scheduled_date=today,
                    scheduled_time=scheduled_time,
                    goal_id=goal["id"] if goal else None,
                    source="goal" if goal else "adaptive",
                    adaptation_metadata=adaptation.metadata,
                )
                session.add(task)
                await session.flush()
                await record_task_event(
                    session,
                    task,
                    "created",
                    actor="system",
                    source="scheduler",
                    to_status=task.status or TaskStatusEnum.pending,
                    metadata={
                        "version": ADAPTATION_VERSION,
                        "goal_id": goal["id"] if goal else None,
                    },
                )
            generated_tasks.append((dim, task_title, difficulty))

        # Send system chat message announcing the tasks
        if generated_tasks:
            hour = local_now().hour
            
            if hour < 6:
                greeting = f"凌晨好，{nickname}"
            elif hour < 12:
                greeting = f"早上好，{nickname}"
            elif hour < 14:
                greeting = f"中午好，{nickname}"
            elif hour < 18:
                greeting = f"下午好，{nickname}"
            else:
                greeting = f"晚上好，{nickname}"
            
            # 使用 markdown 格式，每个任务单独一段
            task_lines = []
            for dim, title, diff in generated_tasks:
                diff_label = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(diff.value, "")
                task_lines.append(f"**【{DIMENSION_LABELS[dim]}】** {title}（{diff_label}）")
            
            content = f"{greeting}！今日任务已发布：\n\n"
            content += "\n\n".join(task_lines)
            content += "\n\n完成后告诉我，我会帮你记录。加油！💪"
            
            msg = Conversation(
                user_id=user_id,
                role=RoleEnum.system,
                content=content,
                extra_metadata={
                    "message_type": "daily_tasks",
                    "greeting": greeting,
                    "scheduled_date": today.isoformat(),
                    "tasks": [
                        {
                            "dimension": dim.value,
                            "title": title,
                            "difficulty": diff.value,
                        }
                        for dim, title, diff in generated_tasks
                    ],
                },
            )
            session.add(msg)

    lock_name = f"task-generation:{user_id}:{local_today().isoformat()}"
    token = await acquire_lock(lock_name, ttl=300)
    if token == "":
        logger.info("Task generation already running for user %s", user_id)
        return
    try:
        if db:
            await _generate(db)
            await db.commit()
            await invalidate_tasks(str(user_id))
        else:
            async with async_session() as session:
                await _generate(session)
                await session.commit()
                await invalidate_tasks(str(user_id))
    finally:
        if token:
            await release_lock(lock_name, token)


async def _generate_skin_based_task(skin_analysis: dict) -> str:
    """根据肤质分析结果生成护肤任务（使用AI动态生成）"""
    issues = skin_analysis.get("issues", [])
    skin_type = skin_analysis.get("skin_type_name", "")
    
    # 调用AI生成个性化护肤任务
    return await generate_skin_task_ai(issues, skin_type)


async def daily_task_generation():
    """Generate daily tasks once for every user in the configured timezone."""
    lock_name = f"daily-task-generation:{local_today().isoformat()}"
    token = await acquire_lock(lock_name, ttl=3600)
    if token == "":
        logger.info("Daily task generation is already owned by another worker")
        return
    try:
        async with async_session() as db:
            changed_users = await maintain_task_states(db)
            for changed_user_id in changed_users:
                await invalidate_tasks(changed_user_id)
            result = await db.execute(select(User))
            users = result.scalars().all()

            for user in users:
                try:
                    await generate_tasks_for_user(user.id, user.nickname, db)
                except Exception:
                    logger.exception("Daily AI task generation failed for user %s", user.id)

            await db.commit()
    finally:
        if token:
            await release_lock(lock_name, token)


async def task_state_maintenance():
    """Wake due snoozes and settle overdue unfinished tasks."""
    async with async_session() as db:
        changed_users = await maintain_task_states(db)
        await db.commit()
    for user_id in changed_users:
        await invalidate_tasks(user_id)


async def daily_task_reminders():
    """Publish a durable morning reminder for users who enabled it."""
    today = local_today()
    async with async_session() as db:
        users_result = await db.execute(select(User))
        for user in users_result.scalars().all():
            task_result = await db.execute(
                select(Task).where(Task.user_id == user.id, Task.scheduled_date == today)
            )
            tasks = [
                task
                for task in task_result.scalars().all()
                if task.status in {TaskStatusEnum.pending, TaskStatusEnum.in_progress}
                or (task.status == TaskStatusEnum.deferred and task.disposition == "snoozed")
            ]
            if not tasks:
                continue
            await create_notification(
                db,
                user_id=user.id,
                kind="daily_tasks",
                title="今日任务已准备",
                message=f"今天有 {len(tasks)} 项任务待推进，点击查看安排。",
                dedupe_key=f"daily-tasks:{today.isoformat()}",
                payload={"link": "/tasks", "task_count": len(tasks)},
                setting_key="daily_tasks",
            )
        await db.commit()


async def scheduled_goal_reminders():
    """Remind once shortly before a task linked to a scheduled growth goal."""
    now = local_now()
    today = now.date()
    async with async_session() as db:
        result = await db.execute(
            select(Task, Goal)
            .join(Goal, Task.goal_id == Goal.id)
            .where(
                Task.scheduled_date == today,
                Task.scheduled_time.isnot(None),
                Task.status.in_([TaskStatusEnum.pending, TaskStatusEnum.in_progress]),
                Goal.status == GoalStatus.active.value,
                Goal.reminder_enabled.is_(True),
            )
        )
        for task, goal in result.all():
            scheduled_at = datetime.combine(
                today,
                task.scheduled_time,
                tzinfo=app_timezone(),
            )
            remind_at = scheduled_at - timedelta(
                minutes=goal.reminder_minutes_before or 0
            )
            if not (remind_at <= now < scheduled_at + timedelta(hours=1)):
                continue
            await create_notification(
                db,
                user_id=task.user_id,
                kind="task_reminder",
                title=f"{task.scheduled_time.strftime('%H:%M')} 的计划快开始了",
                message=task.title,
                dedupe_key=f"goal-task-reminder:{task.id}:{today.isoformat()}",
                payload={
                    "link": "/tasks",
                    "task_id": str(task.id),
                    "goal_id": str(goal.id),
                    "scheduled_time": task.scheduled_time.strftime("%H:%M"),
                },
                setting_key="task_reminders",
            )
        await db.commit()


async def weekly_review_reminders():
    """Publish the weekly review entry point for users who enabled it."""
    review_week_start = last_completed_week_start()
    week_key = review_week_start.isoformat()
    async with async_session() as db:
        users_result = await db.execute(select(User))
        for user in users_result.scalars().all():
            await create_notification(
                db,
                user_id=user.id,
                kind="weekly_review",
                title="上周复盘已准备",
                message="回顾上周完成率、任务调整与成长动量，为本周设置更合适的节奏。",
                dedupe_key=f"weekly-review:{week_key}",
                payload={"link": "/", "week_start": week_key},
                setting_key="weekly_review",
            )
        await db.commit()


def start_scheduler():
    # 每天凌晨 0:00（北京时间）为所有用户生成任务
    # 注意：如果服务器此时未运行，任务会在用户首次查询时自动生成（见 task router）
    if scheduler.running:
        return
    scheduler.add_job(
        daily_task_generation,
        "cron",
        hour=0,
        minute=0,
        id="daily_tasks",
        replace_existing=True,
    )
    scheduler.add_job(
        task_state_maintenance,
        "interval",
        minutes=1,
        id="task_state_maintenance",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        daily_task_reminders,
        "cron",
        hour=8,
        minute=0,
        id="daily_task_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_goal_reminders,
        "interval",
        minutes=1,
        id="scheduled_goal_reminders",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        weekly_review_reminders,
        "cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        id="weekly_review_reminders",
        replace_existing=True,
    )
    scheduler.start()
