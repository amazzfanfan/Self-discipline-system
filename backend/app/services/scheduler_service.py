from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from app.core.database import async_session
from app.models.user import User
from app.models.score import UserScore, DimensionEnum
from app.models.task import Task, DifficultyEnum
from app.services.ai_service import generate_task

scheduler = AsyncIOScheduler()

TASKS_PER_DIMENSION = {
    DimensionEnum.exercise: 1,
    DimensionEnum.diet: 1,
    DimensionEnum.sleep: 1,
    DimensionEnum.appearance: 1,
}


async def daily_task_generation():
    """Generate daily tasks for all users at 8:00."""
    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            # Get user's dimension scores
            scores_result = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
            scores = {s.dimension: s for s in scores_result.scalars().all()}

            for dim, count in TASKS_PER_DIMENSION.items():
                score_record = scores.get(dim)
                if not score_record:
                    continue

                # Determine difficulty based on score
                score_val = float(score_record.score)
                if score_val < 50:
                    difficulty = DifficultyEnum.easy
                elif score_val < 70:
                    difficulty = DifficultyEnum.medium
                else:
                    difficulty = DifficultyEnum.hard

                # AI generates task
                try:
                    task_title = await generate_task(
                        nickname=user.nickname,
                        dimension=dim.value,
                        score=score_val,
                        difficulty=difficulty.value,
                        recent_tasks=[],
                    )
                except Exception:
                    # Fallback to default tasks if AI fails
                    defaults = {
                        DimensionEnum.exercise: "运动30分钟",
                        DimensionEnum.diet: "健康饮食一天",
                        DimensionEnum.sleep: "23:00前入睡",
                        DimensionEnum.appearance: "认真护肤一次",
                    }
                    task_title = defaults[dim]

                task = Task(
                    user_id=user.id,
                    dimension=dim,
                    title=task_title,
                    description="",
                    difficulty=difficulty,
                    scheduled_date=date.today(),
                )
                db.add(task)

        await db.commit()


def start_scheduler():
    scheduler.add_job(daily_task_generation, "cron", hour=8, minute=0, id="daily_tasks")
    scheduler.start()
