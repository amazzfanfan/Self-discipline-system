import asyncio
import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, select
from app.core.config import get_settings
from app.core.database import async_session
from app.core.time import local_now, local_today
from app.models.user import User, UserProfile
from app.models.score import UserScore, DimensionEnum
from app.models.task import Task, DifficultyEnum, TaskStatusEnum
from app.models.conversation import Conversation, RoleEnum
from app.models.goal import GoalStatus
from app.models.behavior import DailyCheckIn
from app.services.ai_service import generate_task
from app.services.faceplus_service import generate_skin_task_ai
from app.services.goal_service import goal_service
from app.services.cache_service import acquire_lock, invalidate_tasks, release_lock

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
            # 按目标类型分组，每个类型取最新的一个目标
            for goal in user_goals:
                goal_type = goal.get("goal_type")
                if goal_type and goal_type not in goals_by_type:
                    goals_by_type[goal_type] = goal.get("content", "")
            print(f"[任务生成] 用户 {user_id} 有 {len(user_goals)} 个活跃目标，覆盖类型: {list(goals_by_type.keys())}")
        except Exception as e:
            print(f"[任务生成] 获取用户目标失败: {e}")

        configured_budget = int(profile.daily_task_budget if profile else 3)
        if checkin and checkin.available_minutes <= 20:
            task_budget = 1
        elif checkin and checkin.available_minutes <= 45:
            task_budget = min(2, configured_budget)
        else:
            task_budget = min(max(configured_budget, 1), 4)
        ordered_dimensions = sorted(
            TASKS_PER_DIMENSION,
            key=lambda dim: (
                0 if dim.value in goals_by_type else 1,
                float(scores[dim].baseline_score) if dim in scores else 100.0,
            ),
        )
        target_dimensions = set(ordered_dimensions[:task_budget])
        if not regenerate_pending and target_dimensions.issubset(existing_dimensions):
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
            dimension_history = [task for task in recent_tasks if task.dimension == dim]
            decided = [task for task in dimension_history if task.status.value in {"completed", "failed"}]
            adherence = (
                sum(task.status.value == "completed" for task in decided) / len(decided)
                if decided else 0.6
            )
            if (checkin and checkin.energy <= 2) or adherence < 0.5:
                difficulty = DifficultyEnum.easy
            elif adherence >= 0.8 and score_val >= 70:
                difficulty = DifficultyEnum.hard
            else:
                difficulty = DifficultyEnum.medium

            goal_content = goals_by_type.get(dim.value)
            if goal_content:
                logger.info(
                    "User %s has a %s goal: %s",
                    user_id,
                    dim.value,
                    goal_content[:50],
                )
            task_specs.append({
                "dimension": dim,
                "difficulty": difficulty,
                "score": score_val,
                "recent_titles": [task.title for task in dimension_history[:6]],
                "goal_content": goal_content,
                "existing_task": existing_task,
            })

        async def _generate_title(spec: dict) -> str:
            dimension = spec["dimension"]
            if (
                dimension == DimensionEnum.appearance
                and isinstance(skin_analysis, dict)
                and skin_analysis.get("source") == "faceplusplus"
            ):
                return await _generate_skin_based_task(skin_analysis)
            return await generate_task(
                nickname=nickname,
                dimension=dimension.value,
                score=spec["score"],
                difficulty=spec["difficulty"].value,
                recent_tasks=spec["recent_titles"],
                goal_content=spec["goal_content"],
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
            task_title = generated_title[:200]
            rationale = (
                "根据今日精力与近期完成率降低难度"
                if difficulty == DifficultyEnum.easy
                else "结合画像基线、目标和近期完成情况由 AI 生成"
            )
            estimated_minutes = {
                DifficultyEnum.easy: "10-20",
                DifficultyEnum.medium: "20-40",
                DifficultyEnum.hard: "40-60",
            }[difficulty]
            task = spec["existing_task"]
            if task:
                task.title = task_title
                task.rationale = rationale
                task.estimated_minutes = estimated_minutes
                task.difficulty = difficulty
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
                )
                session.add(task)
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
    scheduler.start()
