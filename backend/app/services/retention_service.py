from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import async_session
from app.models.agent_run import AgentRun, AgentStep, PendingAction
from app.models.notification import UserNotification
from app.models.user import User, UserProfile
from app.services.upload_service import UPLOAD_DIRECTORY, delete_saved_image


PHOTO_FIELDS = (
    "avatar_url",
    "portrait_photo_url",
    "front_photo_url",
    "side_photo_url",
)


def _stored_filename(value: str | None) -> str | None:
    if not value:
        return None
    name = Path(value).name
    return name if name else None


def _is_older_than(path: Path, cutoff: datetime) -> bool:
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return modified_at < cutoff


async def cleanup_upload_files(db, *, now: datetime | None = None) -> dict[str, int]:
    """Remove expired retained photos and stale unreferenced uploads."""
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    profile_rows = (await db.execute(select(UserProfile))).scalars().all()
    user_rows = (await db.execute(select(User))).scalars().all()

    references: dict[str, list[tuple[object, str]]] = {}
    for profile in profile_rows:
        for field in PHOTO_FIELDS:
            filename = _stored_filename(getattr(profile, field, None))
            if filename:
                references.setdefault(filename, []).append((profile, field))
    for user in user_rows:
        filename = _stored_filename(user.avatar_url)
        if filename:
            references.setdefault(filename, []).append((user, "avatar_url"))

    retained_deleted = 0
    photo_days = max(0, settings.PHOTO_RETENTION_DAYS)
    if photo_days:
        retained_cutoff = now - timedelta(days=photo_days)
        for filename, owners in list(references.items()):
            path = (UPLOAD_DIRECTORY / filename).resolve()
            if path.parent != UPLOAD_DIRECTORY or not path.is_file():
                for owner, field in owners:
                    setattr(owner, field, None)
                references.pop(filename, None)
                continue
            if _is_older_than(path, retained_cutoff):
                for owner, field in owners:
                    setattr(owner, field, None)
                await delete_saved_image(path)
                references.pop(filename, None)
                retained_deleted += 1

    orphan_deleted = 0
    orphan_cutoff = now - timedelta(hours=max(1, settings.TEMP_UPLOAD_RETENTION_HOURS))
    if UPLOAD_DIRECTORY.is_dir():
        known = set(references)
        for path in await asyncio.to_thread(lambda: list(UPLOAD_DIRECTORY.glob("*.jpg"))):
            if path.name not in known and _is_older_than(path, orphan_cutoff):
                await asyncio.to_thread(path.unlink, missing_ok=True)
                orphan_deleted += 1

    return {
        "retained_photos_deleted": retained_deleted,
        "orphan_uploads_deleted": orphan_deleted,
    }


async def cleanup_expired_data(*, now: datetime | None = None) -> dict[str, int]:
    """Apply configured privacy retention windows to operational data."""
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    trace_cutoff = now - timedelta(days=max(1, settings.TRACE_RETENTION_DAYS))
    notification_cutoff = now - timedelta(days=max(1, settings.NOTIFICATION_RETENTION_DAYS))

    async with async_session() as db:
        expired_runs = select(AgentRun.id).where(AgentRun.created_at < trace_cutoff)
        steps_result = await db.execute(
            delete(AgentStep).where(AgentStep.agent_run_id.in_(expired_runs))
        )
        actions_result = await db.execute(
            delete(PendingAction).where(
                (PendingAction.expires_at < now)
                | (PendingAction.created_at < trace_cutoff)
            )
        )
        runs_result = await db.execute(delete(AgentRun).where(AgentRun.created_at < trace_cutoff))
        notifications_result = await db.execute(
            delete(UserNotification).where(UserNotification.created_at < notification_cutoff)
        )
        photo_counts = await cleanup_upload_files(db, now=now)
        await db.commit()

    return {
        "agent_steps_deleted": steps_result.rowcount or 0,
        "pending_actions_deleted": actions_result.rowcount or 0,
        "agent_runs_deleted": runs_result.rowcount or 0,
        "notifications_deleted": notifications_result.rowcount or 0,
        **photo_counts,
    }
