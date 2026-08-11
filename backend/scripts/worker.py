"""Local Redis Stream worker for durable post-response jobs.

Run with: ``python -m scripts.worker``
"""

import asyncio
import json
import logging
import socket
import uuid

from app.core.database import async_session, engine
from app.services.cache_service import acknowledge_background_job, read_background_jobs
from app.services.memory_service import MemoryService
from app.services.goal_service import goal_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("system-agent.worker")


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
        logger.warning("Unknown job kind: %s", kind)


async def main() -> None:
    consumer = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    logger.info("Background worker started: %s", consumer)
    try:
        while True:
            try:
                streams = await read_background_jobs(consumer)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis Stream read failed; retrying")
                await asyncio.sleep(1)
                continue
            for _, messages in streams:
                for message_id, fields in messages:
                    try:
                        await process_job(fields["kind"], json.loads(fields["payload"]))
                    except Exception:
                        logger.exception("Background job failed: %s", message_id)
                        continue
                    await acknowledge_background_job(message_id)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
