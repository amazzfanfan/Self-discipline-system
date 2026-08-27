from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import async_session
from app.models.assessment import AssessmentRun
from app.models.conversation import Conversation
from app.models.user import User, UserProfile
from app.services.faceplus_service import generate_ai_suggestions_safely
from app.services.notification_service import create_notification
from app.services.scheduler_service import generate_tasks_for_user


def generation_payload(run: AssessmentRun) -> dict:
    return {
        "assessment_id": str(run.id),
        "status": run.generation_status,
        "stage": run.generation_stage,
        "error": run.generation_error,
        "care_suggestions": list(run.care_suggestions or []),
        "started_at": run.generation_started_at.isoformat() if run.generation_started_at else None,
        "completed_at": (
            run.generation_completed_at.isoformat() if run.generation_completed_at else None
        ),
    }


async def _set_stage(db, run: AssessmentRun, stage: str) -> None:
    run.generation_status = "running"
    run.generation_stage = stage
    run.generation_error = None
    if run.generation_started_at is None:
        run.generation_started_at = datetime.now(timezone.utc)
    await db.commit()


async def process_assessment_generation(assessment_run_id: str, user_id: str) -> None:
    """Generate AI care advice and daily tasks as a recoverable background job."""
    async with async_session() as db:
        run = await db.scalar(
            select(AssessmentRun).where(
                AssessmentRun.id == assessment_run_id,
                AssessmentRun.user_id == user_id,
            )
        )
        if run is None or run.generation_status == "completed":
            return

        try:
            user = await db.scalar(select(User).where(User.id == user_id))
            profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
            if user is None:
                raise RuntimeError("assessment user no longer exists")

            await _set_stage(db, run, "care_suggestions")
            skin_analysis = profile.skin_analysis if profile and isinstance(profile.skin_analysis, dict) else None
            suggestions: list[str] = []
            suggestions_error = None
            if skin_analysis and skin_analysis.get("source") == "faceplusplus":
                suggestions, suggestions_error = await generate_ai_suggestions_safely(
                    list(skin_analysis.get("issues") or []),
                    str(skin_analysis.get("skin_type_name") or "未知"),
                    profile.skincare_constraints if profile else None,
                    profile.task_constraints if profile else None,
                )
                suggestions = suggestions[:3]
                profile.skin_analysis = {
                    **skin_analysis,
                    "suggestions": suggestions,
                    "suggestions_error": suggestions_error,
                }

            run.care_suggestions = suggestions
            if run.profile_message_id:
                message = await db.get(Conversation, run.profile_message_id)
                if message:
                    message.extra_metadata = {
                        **(message.extra_metadata or {}),
                        "care_suggestions": suggestions,
                        "care_suggestions_error": suggestions_error,
                        "generation_status": "care_ready",
                    }
            await db.commit()

            await _set_stage(db, run, "daily_tasks")
            await generate_tasks_for_user(
                user.id,
                user.nickname,
                db,
                regenerate_pending=True,
            )

            run.generation_status = "completed"
            run.generation_stage = "completed"
            run.generation_error = None
            run.generation_completed_at = datetime.now(timezone.utc)
            if run.profile_message_id:
                message = await db.get(Conversation, run.profile_message_id)
                if message:
                    message.extra_metadata = {
                        **(message.extra_metadata or {}),
                        "generation_status": "completed",
                    }
            await create_notification(
                db,
                user_id=user.id,
                kind="system",
                title="个性化方案已生成",
                message="AI 护理建议和今日任务已经准备好。",
                dedupe_key=f"assessment-generation:{run.id}",
                payload={"link": "/chat", "assessment_id": str(run.id)},
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            failed_run = await db.get(AssessmentRun, assessment_run_id)
            if failed_run:
                failed_run.generation_status = "failed"
                failed_run.generation_stage = "failed"
                failed_run.generation_error = type(exc).__name__[:120]
                await db.commit()
            raise
