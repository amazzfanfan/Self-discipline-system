from datetime import date, datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from app.core.database import async_session
from app.models.user import User
from app.models.score import UserScore, DimensionEnum
from app.models.task import Task, DifficultyEnum
from app.models.conversation import Conversation, RoleEnum
from app.services.ai_service import generate_task

scheduler = AsyncIOScheduler()

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
    DimensionEnum.appearance: "外貌",
}


async def generate_tasks_for_user(user_id, nickname: str, db=None):
    """Generate today's tasks for a single user. Pass db session or creates its own."""
    async def _generate(session):
        scores_result = await session.execute(select(UserScore).where(UserScore.user_id == user_id))
        scores = {s.dimension: s for s in scores_result.scalars().all()}

        generated_tasks = []
        default_titles = {
            DimensionEnum.exercise: "运动30分钟",
            DimensionEnum.diet: "健康饮食一天",
            DimensionEnum.sleep: "23:00前入睡",
            DimensionEnum.appearance: "认真护肤一次",
        }

        for dim, count in TASKS_PER_DIMENSION.items():
            score_record = scores.get(dim)
            if not score_record:
                continue

            score_val = float(score_record.score)
            if score_val < 50:
                difficulty = DifficultyEnum.easy
            elif score_val < 70:
                difficulty = DifficultyEnum.medium
            else:
                difficulty = DifficultyEnum.hard

            try:
                task_title = await generate_task(
                    nickname=nickname,
                    dimension=dim.value,
                    score=score_val,
                    difficulty=difficulty.value,
                    recent_tasks=[],
                )
            except Exception:
                task_title = default_titles[dim]

            # Safety: truncate task title to 200 chars
            task_title = (task_title or default_titles.get(dim, "完成一个今日任务"))[:200]

            task = Task(
                user_id=user_id,
                dimension=dim,
                title=task_title,
                description="",
                difficulty=difficulty,
                scheduled_date=date.today(),
            )
            session.add(task)
            generated_tasks.append((dim, task_title, difficulty))

        # Send system chat message announcing the tasks
        if generated_tasks:
            hour = datetime.now(timezone.utc).hour
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
            lines = [f"{greeting}！今日任务已发布：\n"]
            for dim, title, diff in generated_tasks:
                diff_label = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(diff.value, "")
                lines.append(f"【{DIMENSION_LABELS[dim]}】{title}（{diff_label}）")
            lines.append("\n完成后告诉我，我会帮你记录。加油！💪")
            msg = Conversation(
                user_id=user_id,
                role=RoleEnum.system,
                content="\n".join(lines),
            )
            session.add(msg)

    if db:
        await _generate(db)
    else:
        async with async_session() as session:
            await _generate(session)
            await session.commit()


async def daily_task_generation():
    """Generate daily tasks for all users at 8:00."""
    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            await generate_tasks_for_user(user.id, user.nickname, db)

        await db.commit()


def start_scheduler():
    scheduler.add_job(daily_task_generation, "cron", hour=8, minute=0, id="daily_tasks")
    scheduler.start()
