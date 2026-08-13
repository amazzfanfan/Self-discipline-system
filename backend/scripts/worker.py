"""Local Redis Stream worker for durable post-response jobs.

Run with: ``python -m scripts.worker``
"""

import asyncio
import json
import logging
import socket
import time
import uuid

from app.core.database import async_session, engine
from app.core.config import get_settings
from app.services.cache_service import (
    acknowledge_background_job,
    claim_stale_background_jobs,
    move_background_job_to_dead_letter,
    read_background_jobs,
    record_background_job_failure,
    set_background_worker_heartbeat,
)
from app.services.memory_service import MemoryService
from app.services.goal_service import goal_service
from app.services.assessment_generation_service import process_assessment_generation
from app.services.scheduler_service import generate_tasks_for_user
from app.services.llm_service import begin_llm_metrics
from app.services.metrics_service import increment_metric
from app.models.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("system-agent.worker")
settings = get_settings()
MAX_JOB_ATTEMPTS = 3
STALE_JOB_IDLE_MS = settings.WORKER_STALE_JOB_IDLE_MS
HEARTBEAT_INTERVAL_SECONDS = 5
AI_JOB_KINDS = {
    "learn_from_user",
    "index_goal",
    "refresh_goal_tasks",
    "generate_assessment_extras",
}


async def process_job(kind: str, payload: dict) -> None:
    async with async_session() as session:
        if kind == "learn_from_user":
            await MemoryService(session).auto_store_conversation(
                user_id=payload["user_id"],
                content=payload["content"],
                role="user",
                source_id=payload["user_message_id"],
            )
            return
        if kind == "index_goal":
            await goal_service.index_goal_embedding(
                db=session,
                goal_id=payload["goal_id"],
                user_id=payload["user_id"],
            )
            return
        if kind == "refresh_goal_tasks":
            user = await session.get(User, payload["user_id"])
            if user:
                await generate_tasks_for_user(
                    user.id,
                    user.nickname,
                    session,
                    regenerate_pending=True,
                )
            return
        if kind == "generate_assessment_extras":
            await process_assessment_generation(
                assessment_run_id=payload["assessment_run_id"],
                user_id=payload["user_id"],
            )
            return
        logger.warning("Unknown job kind: %s", kind)


async def handle_message(message_id: str, fields: dict) -> None:
    started = time.perf_counter()
    kind = str(fields.get("kind", "unknown"))
    try:
        payload = json.loads(fields["payload"])
        begin_llm_metrics(str(payload.get("user_id")) if payload.get("user_id") else None)
        await process_job(kind, payload)
    except Exception as exc:
        await increment_metric(f"worker:{kind}:failed")
        attempts = await record_background_job_failure(message_id)
        if attempts >= MAX_JOB_ATTEMPTS:
            await move_background_job_to_dead_letter(
                message_id,
                fields,
                attempts=attempts,
                error_type=type(exc).__name__,
            )
            logger.exception(
                "Background job moved to dead-letter after %s attempts: %s",
                attempts,
                message_id,
            )
        else:
            logger.exception(
                "Background job failed (attempt %s/%s); it will be reclaimed: %s",
                attempts,
                MAX_JOB_ATTEMPTS,
                message_id,
            )
        return
    await acknowledge_background_job(message_id)
    await increment_metric(f"worker:{kind}:completed")
    duration_ms = int((time.perf_counter() - started) * 1000)
    if duration_ms >= 30_000:
        await increment_metric(f"worker:{kind}:slow")


async def handle_message_with_limits(
    message_id: str,
    fields: dict,
    worker_semaphore: asyncio.Semaphore,
    ai_semaphore: asyncio.Semaphore,
) -> None:
    async with worker_semaphore:
        if fields.get("kind") in AI_JOB_KINDS:
            async with ai_semaphore:
                await handle_message(message_id, fields)
        else:
            await handle_message(message_id, fields)


async def heartbeat_loop(consumer: str) -> None:
    while True:
        try:
            await set_background_worker_heartbeat(consumer)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Background worker heartbeat failed")
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def main() -> None:
    consumer = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    logger.info("Background worker started: %s", consumer)
    heartbeat_task = asyncio.create_task(heartbeat_loop(consumer))
    worker_semaphore = asyncio.Semaphore(max(1, settings.WORKER_CONCURRENCY))
    ai_semaphore = asyncio.Semaphore(max(1, settings.WORKER_AI_CONCURRENCY))
    try:
        while True:
            try:
                claimed = await claim_stale_background_jobs(
                    consumer,
                    min_idle_ms=STALE_JOB_IDLE_MS,
                )
                streams = [] if claimed else await read_background_jobs(
                    consumer,
                    count=max(1, settings.WORKER_BATCH_SIZE),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis Stream read failed; retrying")
                await asyncio.sleep(1)
                continue
            messages = claimed or [message for _, items in streams for message in items]
            await asyncio.gather(*(
                handle_message_with_limits(
                    message_id,
                    fields,
                    worker_semaphore,
                    ai_semaphore,
                )
                for message_id, fields in messages
            ))
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
