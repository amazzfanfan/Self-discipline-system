from datetime import date, datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from app.core.database import async_session
from app.models.user import User, UserProfile
from app.models.score import UserScore, DimensionEnum
from app.models.task import Task, DifficultyEnum
from app.models.conversation import Conversation, RoleEnum
from app.services.ai_service import generate_task
from app.services.faceplus_service import generate_skin_task

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

        # 获取用户的肤质分析结果
        profile_result = await session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        skin_analysis = profile.skin_analysis if profile else None

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

            # 对于外貌维度，如果有肤质分析结果，生成针对性任务
            if dim == DimensionEnum.appearance and skin_analysis:
                task_title = _generate_skin_based_task(skin_analysis)
            else:
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
            # 使用北京时间 (UTC+8)
            from datetime import timedelta
            bj_time = datetime.now(timezone.utc) + timedelta(hours=8)
            hour = bj_time.hour
            
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
            )
            session.add(msg)

    if db:
        await _generate(db)
    else:
        async with async_session() as session:
            await _generate(session)
            await session.commit()


def _generate_skin_based_task(skin_analysis: dict) -> str:
    """根据肤质分析结果生成护肤任务"""
    issues = skin_analysis.get("issues", [])
    skin_type = skin_analysis.get("skin_type_name", "")
    
    if not issues:
        # 没有明显问题，生成日常护理任务
        if skin_type == "油性":
            return "使用控油洁面乳清洁面部，配合清爽型保湿"
        elif skin_type == "干性":
            return "使用温和洁面乳，配合滋润型保湿霜"
        elif skin_type == "混合性":
            return "T区控油清洁，两颊重点保湿"
        else:
            return "认真护肤一次，保持良好状态"
    
    # 根据主要问题生成任务
    main_issue = issues[0]
    
    task_map = {
        "黑眼圈": "使用眼霜按摩眼周5分钟，晚上11点前入睡",
        "眼袋": "冷敷眼部10分钟，减少睡前饮水",
        "额头皱纹": "使用抗皱精华按摩额头，注意防晒",
        "法令纹": "做面部按摩提升，使用抗皱精华",
        "鱼尾纹": "使用眼霜按摩眼周，避免过度眯眼",
        "眉间皱纹": "放松眉头，使用抗皱精华按摩",
        "眼部细纹": "使用眼霜轻拍眼周，保持眼部湿润",
        "痘痘": "认真清洁面部，使用祛痘产品",
        "黑头": "使用清洁面膜，配合收敛水",
        "皮肤斑点": "使用美白精华，注意防晒",
        "额头毛孔粗大": "使用收敛水湿敷额头5分钟",
        "左脸颊毛孔粗大": "使用收敛水湿敷脸颊5分钟",
        "右脸颊毛孔粗大": "使用收敛水湿敷脸颊5分钟",
        "下巴毛孔粗大": "使用清洁面膜，配合收敛水",
    }
    
    base_task = task_map.get(main_issue, "认真护肤一次")
    
    # 如果有多个问题，追加次要任务
    if len(issues) > 1:
        secondary = issues[1]
        if secondary in ["黑眼圈", "眼袋", "眼部细纹"]:
            base_task += "，睡前使用眼霜"
        elif secondary in ["痘痘", "黑头"]:
            base_task += "，注意饮食清淡"
    
    return base_task


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
