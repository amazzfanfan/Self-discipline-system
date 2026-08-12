from __future__ import annotations

from sqlalchemy import select

from app.models.goal import Goal
from app.models.score import UserScore
from app.models.task import Task
from app.models.user import User, UserProfile
from app.services.ai_service import generate_task
from app.services.faceplus_service import generate_skin_task_ai
from app.services.task_constraint_service import validate_task_feasibility


async def generate_ai_task_replacement(
    db,
    *,
    user_id,
    task: Task,
    profile: UserProfile,
) -> str:
    """Generate a constraint-safe replacement with AI; never use a rule template."""
    user = await db.get(User, user_id)
    score = await db.scalar(
        select(UserScore).where(
            UserScore.user_id == user_id,
            UserScore.dimension == task.dimension,
        )
    )
    goal = await db.get(Goal, task.goal_id) if task.goal_id else None
    constraints = profile.task_constraints or {}
    candidate = ""
    last_error: Exception | None = None

    for _ in range(2):
        try:
            skin = profile.skin_analysis or {}
            if task.dimension.value == "appearance" and skin.get("source") == "faceplusplus":
                candidate = await generate_skin_task_ai(
                    skin.get("issues") or [],
                    skin.get("skin_type_name") or "未知",
                    profile.skincare_constraints,
                    constraints,
                )
            else:
                candidate = await generate_task(
                    nickname=user.nickname if user else "用户",
                    dimension=task.dimension.value,
                    score=float(score.score) if score else 50.0,
                    difficulty=(
                        task.difficulty.value
                        if hasattr(task.difficulty, "value")
                        else str(task.difficulty or "medium")
                    ),
                    recent_tasks=[task.title],
                    goal_content=goal.content if goal else None,
                    adaptation_context=(
                        f"当前任务“{task.title}”与用户新提供的可执行条件冲突。"
                        "生成同维度、目标相近但行动方式不同的替代任务；不得复述原任务。"
                    ),
                    task_constraints=constraints,
                )
            feasible, reason = validate_task_feasibility(candidate, constraints)
            if feasible and candidate.strip() != task.title.strip():
                return candidate.strip()[:200]
            last_error = RuntimeError(reason or "AI returned the original task")
        except Exception as exc:  # Surface an explicit unavailable state after retries.
            last_error = exc
    raise RuntimeError("AI 暂时无法生成满足当前条件的替代任务") from last_error
