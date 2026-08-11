from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.models.agent_run import AgentRun, AgentStep, PendingAction
from app.models.assessment import AssessmentRun
from app.models.behavior import DailyCheckIn, WeeklyReview
from app.models.conversation import Conversation
from app.models.goal import Goal
from app.models.memory import Memory
from app.models.notification import UserNotification
from app.models.score import ScoreHistory, UserScore
from app.models.task import Task, TaskEvent
from app.models.user import User, UserProfile
from app.models.weight import WeightRecord
from app.services.cache_service import revoke_all_refresh_sessions
from app.services.upload_service import delete_saved_image


async def export_user_data(db, user: User) -> dict:
    async def all_items(model):
        result = await db.execute(select(model).where(model.user_id == user.id))
        return result.scalars().all()

    profile = user.profile
    scores = await all_items(UserScore)
    tasks = await all_items(Task)
    task_events = await all_items(TaskEvent)
    conversations = await all_items(Conversation)
    memories = await all_items(Memory)
    goals = await all_items(Goal)
    weights = await all_items(WeightRecord)
    assessments = await all_items(AssessmentRun)
    checkins = await all_items(DailyCheckIn)
    reviews = await all_items(WeeklyReview)
    runs = await all_items(AgentRun)
    notifications = await all_items(UserNotification)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "id": str(user.id),
            "email": user.email,
            "nickname": user.nickname,
            "created_at": user.created_at.isoformat(),
        },
        "profile": {
            "height_cm": float(profile.height_cm) if profile and profile.height_cm else None,
            "weight_kg": float(profile.weight_kg) if profile and profile.weight_kg else None,
            "age": profile.age if profile else None,
            "gender": profile.gender.value if profile and profile.gender else None,
            "questionnaire": profile.questionnaire if profile else None,
            "skin_analysis": profile.skin_analysis if profile else None,
            "memory_enabled": bool(profile.memory_enabled) if profile else True,
            "daily_task_budget": profile.daily_task_budget if profile else 3,
        },
        "scores": [
            {
                "dimension": item.dimension.value,
                "baseline": float(item.baseline_score),
                "streak_days": item.streak_days,
                "last_completed_date": (
                    item.last_completed_date.isoformat() if item.last_completed_date else None
                ),
            }
            for item in scores
        ],
        "tasks": [
            {
                "id": str(item.id),
                "dimension": item.dimension.value,
                "title": item.title,
                "date": item.scheduled_date.isoformat(),
                "status": item.status.value,
                "feedback": item.user_feedback,
            }
            for item in tasks
        ],
        "task_events": [
            {
                "id": str(item.id),
                "task_id": str(item.task_id),
                "event_type": item.event_type,
                "from_status": item.from_status,
                "to_status": item.to_status,
                "reason": item.reason,
                "actor": item.actor,
                "source": item.source,
                "metadata": item.event_metadata,
                "created_at": item.created_at.isoformat(),
            }
            for item in task_events
        ],
        "conversations": [
            {"role": item.role.value, "content": item.content, "created_at": item.created_at.isoformat()}
            for item in conversations
        ],
        "memories": [item.to_dict() | {"content": item.content} for item in memories],
        "goals": [item.to_dict() for item in goals],
        "weights": [
            {"weight_kg": float(item.weight_kg), "recorded_at": item.recorded_at.isoformat()}
            for item in weights
        ],
        "assessments": [
            {
                "id": str(item.id),
                "rubric_version": item.rubric_version,
                "scores": item.scores,
                "evidence": item.evidence,
                "generation_status": item.generation_status,
                "generation_stage": item.generation_stage,
                "care_suggestions": item.care_suggestions,
                "created_at": item.created_at.isoformat(),
            }
            for item in assessments
        ],
        "checkins": [
            {
                "date": item.checkin_date.isoformat(),
                "sleep_hours": float(item.sleep_hours) if item.sleep_hours is not None else None,
                "energy": item.energy,
                "mood": item.mood,
                "stress": item.stress,
                "available_minutes": item.available_minutes,
                "note": item.note,
            }
            for item in checkins
        ],
        "weekly_reviews": [item.summary for item in reviews],
        "agent_runs": [
            {"run_id": item.run_id, "status": item.status, "metrics": item.metrics, "created_at": item.created_at.isoformat()}
            for item in runs
        ],
        "notifications": [
            {
                "kind": item.kind,
                "title": item.title,
                "message": item.message,
                "read_at": item.read_at.isoformat() if item.read_at else None,
                "created_at": item.created_at.isoformat(),
            }
            for item in notifications
        ],
    }


async def delete_user_account(db, user: User) -> None:
    # Load explicitly instead of relying on async ORM lazy loading. This keeps
    # the service safe when called from workers, scripts, or tests where the
    # relationship was not eagerly populated by the auth dependency.
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    photos = []
    if profile:
        photos = [
            profile.avatar_url,
            profile.portrait_photo_url,
            profile.front_photo_url,
            profile.side_photo_url,
        ]
    run_ids = select(AgentRun.id).where(AgentRun.user_id == user.id)
    await db.execute(delete(AgentStep).where(AgentStep.agent_run_id.in_(run_ids)))
    for model in (
        PendingAction,
        AgentRun,
        AssessmentRun,
        ScoreHistory,
        Task,
        Conversation,
        Memory,
        Goal,
        WeightRecord,
        DailyCheckIn,
        WeeklyReview,
        UserNotification,
        UserScore,
        UserProfile,
    ):
        await db.execute(delete(model).where(model.user_id == user.id))
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    for photo in photos:
        await delete_saved_image(photo)
    await revoke_all_refresh_sessions(str(user.id))
