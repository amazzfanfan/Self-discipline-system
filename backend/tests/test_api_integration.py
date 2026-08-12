import asyncio
import os
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine, get_db
from app.core.deps import get_current_user
from app.core.time import local_today
from app.main import app
from app.models.assessment import AssessmentRun
from app.models.notification import UserNotification
from app.models.score import DimensionEnum, UserScore
from app.models.task import DifficultyEnum, Task, TaskEvent, TaskStatusEnum
from app.models.user import User, UserProfile


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="set RUN_DB_INTEGRATION=1 with a migrated PostgreSQL test database",
)


async def _exercise_api_contracts(monkeypatch):
    import app.modules.task.router as task_router
    import app.modules.user.router as user_router
    import app.services.goal_service as goal_service_module

    monkeypatch.setattr(task_router, "invalidate_tasks", AsyncMock())
    monkeypatch.setattr(task_router, "invalidate_scores", AsyncMock())
    monkeypatch.setattr(goal_service_module, "enqueue_background_job", AsyncMock(return_value="1-0"))
    enqueue_assessment = AsyncMock(return_value="1-0")
    monkeypatch.setattr(user_router, "enqueue_background_job_once", enqueue_assessment)

    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            user = User(
                id=uuid.uuid4(),
                email=f"integration-{uuid.uuid4().hex}@example.com",
                password_hash="not-used",
                nickname="集成测试用户",
            )
            session.add(user)
            await session.flush()
            session.add(UserProfile(user_id=user.id, daily_task_budget=3))
            for dimension in DimensionEnum:
                session.add(
                    UserScore(
                        user_id=user.id,
                        dimension=dimension,
                        score=60,
                        baseline_score=60,
                    )
                )
            task = Task(
                id=uuid.uuid4(),
                user_id=user.id,
                dimension=DimensionEnum.exercise,
                title="完成 20 分钟快走",
                difficulty=DifficultyEnum.easy,
                scheduled_date=local_today(),
                status=TaskStatusEnum.pending,
            )
            session.add(task)
            assessment = AssessmentRun(
                id=uuid.uuid4(),
                user_id=user.id,
                input_hash=uuid.uuid4().hex,
                rubric_version="integration-v1",
                mode="rules",
                scores={dimension.value: 60 for dimension in DimensionEnum},
                evidence={},
                confidence={dimension.value: 1 for dimension in DimensionEnum},
                overall_confidence=1,
                warnings=[],
                generation_status="pending",
                generation_stage="queued",
                care_suggestions=[],
            )
            session.add(assessment)
            notification = UserNotification(
                id=uuid.uuid4(),
                user_id=user.id,
                kind="system",
                title="测试通知",
                message="等待读取",
                dedupe_key=f"integration:{uuid.uuid4().hex}",
            )
            session.add(notification)
            await session.flush()

            async def override_db():
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

            async def override_user():
                return user

            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_current_user] = override_user
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                complete_response = await client.post(f"/api/tasks/{task.id}/complete")
                assert complete_response.status_code == 200
                await session.refresh(task)
                assert task.status == TaskStatusEnum.completed
                exercise_score = await session.scalar(
                    select(UserScore).where(
                        UserScore.user_id == user.id,
                        UserScore.dimension == DimensionEnum.exercise,
                    )
                )
                assert exercise_score.streak_days == 1
                assert exercise_score.last_completed_date == local_today()
                task_events = (
                    await session.execute(
                        select(TaskEvent).where(TaskEvent.task_id == task.id)
                    )
                ).scalars().all()
                assert [event.event_type for event in task_events] == ["completed"]
                timeline_response = await client.get(f"/api/tasks/{task.id}/events")
                assert timeline_response.status_code == 200
                assert timeline_response.json()[0]["source"] == "api"

                metrics_response = await client.get("/api/behavior/metrics")
                assert metrics_response.status_code == 200
                assert metrics_response.json()["overall"]["sample_count_7d"] == 1

                goal_response = await client.post(
                    "/api/goals",
                    json={
                        "content": "每天晚上八点快走四十分钟",
                        "goal_type": "exercise",
                        "target_metric": "weekly_sessions",
                        "target_value": 7,
                        "recurrence": "daily",
                        "preferred_time": "20:00",
                        "duration_minutes": 40,
                        "reminder_enabled": True,
                    },
                )
                assert goal_response.status_code == 200
                goal_id = goal_response.json()["id"]
                assert goal_response.json()["preferred_time"] == "20:00"
                assert goal_response.json()["duration_minutes"] == 40
                pause_response = await client.put(
                    f"/api/goals/{goal_id}",
                    json={"status": "paused"},
                )
                assert pause_response.status_code == 200
                assert pause_response.json()["status"] == "paused"
                paused_goals = await client.get("/api/goals?status=paused")
                assert [item["id"] for item in paused_goals.json()] == [goal_id]

                calendar_response = await client.get(
                    "/api/tasks",
                    params={
                        "start_date": local_today().isoformat(),
                        "end_date": local_today().isoformat(),
                    },
                )
                assert calendar_response.status_code == 200
                assert calendar_response.json()[0]["scheduled_date"] == local_today().isoformat()

                inbox_response = await client.get("/api/notifications?unread_only=true")
                assert inbox_response.status_code == 200
                assert inbox_response.json()["unread_count"] == 1
                read_response = await client.post(f"/api/notifications/{notification.id}/read")
                assert read_response.status_code == 200
                assert read_response.json()["read_at"] is not None

                assessment_response = await client.get("/api/users/me/assessment/latest")
                assert assessment_response.status_code == 200
                assert assessment_response.json()["generation"]["status"] == "pending"
                enqueue_assessment.assert_awaited()
        finally:
            app.dependency_overrides.clear()
            await session.close()
            await outer_transaction.rollback()


def test_authenticated_api_workflows_persist_consistently(monkeypatch):
    asyncio.run(_exercise_api_contracts(monkeypatch))
