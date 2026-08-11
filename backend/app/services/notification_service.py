from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import UserNotification
from app.models.user import UserProfile


SETTING_DEFAULTS = {
    "task_reminders": True,
    "daily_tasks": False,
    "weekly_review": False,
}


async def notification_enabled(db: AsyncSession, user_id, setting_key: str) -> bool:
    result = await db.execute(
        select(UserProfile.notification_settings).where(UserProfile.user_id == user_id)
    )
    settings = result.scalar_one_or_none() or {}
    return bool(settings.get(setting_key, SETTING_DEFAULTS.get(setting_key, True)))


async def create_notification(
    db: AsyncSession,
    *,
    user_id,
    kind: str,
    title: str,
    message: str,
    dedupe_key: str,
    payload: dict | None = None,
    setting_key: str | None = None,
) -> UserNotification | None:
    """Create an idempotent user notification, respecting the related preference."""
    if setting_key and not await notification_enabled(db, user_id, setting_key):
        return None
    existing_result = await db.execute(
        select(UserNotification).where(
            and_(
                UserNotification.user_id == user_id,
                UserNotification.dedupe_key == dedupe_key,
            )
        )
    )
    if existing_result.scalar_one_or_none():
        return None
    item = UserNotification(
        user_id=user_id,
        kind=kind[:30],
        title=title[:120],
        message=message[:500],
        payload=payload or {},
        dedupe_key=dedupe_key[:160],
    )
    db.add(item)
    return item

