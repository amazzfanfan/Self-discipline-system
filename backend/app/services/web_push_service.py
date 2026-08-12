from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session
from app.core.time import local_now
from app.models.notification import PushSubscription, UserNotification
from app.models.user import UserProfile

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # The feature is optional; station notifications must remain usable.
    WebPushException = Exception
    webpush = None


logger = logging.getLogger(__name__)
settings = get_settings()


def web_push_configured() -> bool:
    return bool(
        webpush
        and settings.WEB_PUSH_VAPID_PUBLIC_KEY.strip()
        and settings.WEB_PUSH_VAPID_PRIVATE_KEY.strip()
        and settings.WEB_PUSH_VAPID_EMAIL.strip()
    )


def web_push_public_config() -> dict:
    return {
        "enabled": web_push_configured(),
        "public_key": settings.WEB_PUSH_VAPID_PUBLIC_KEY if web_push_configured() else None,
    }


def within_quiet_hours(
    current: time,
    start: time | None,
    end: time | None,
) -> bool:
    if start is None or end is None or start == end:
        return False
    current = current.replace(tzinfo=None)
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _send(subscription: PushSubscription, notification: UserNotification) -> None:
    if webpush is None:
        raise RuntimeError("pywebpush is not installed")
    payload = {
        "notification_id": str(notification.id),
        "title": notification.title,
        "body": notification.message,
        "kind": notification.kind,
        "link": (notification.payload or {}).get("link", "/"),
    }
    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=settings.WEB_PUSH_VAPID_PRIVATE_KEY,
        vapid_claims={"sub": settings.WEB_PUSH_VAPID_EMAIL},
        ttl=300,
    )


async def deliver_pending_web_push() -> dict:
    """Deliver recent unread station notifications to registered browsers once."""
    if not web_push_configured():
        return {"enabled": False, "sent": 0, "failed": 0, "removed": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    sent = failed = removed = 0
    async with async_session() as db:
        result = await db.execute(
            select(UserNotification, UserProfile)
            .join(UserProfile, UserProfile.user_id == UserNotification.user_id)
            .where(
                UserNotification.push_sent_at.is_(None),
                UserNotification.read_at.is_(None),
                UserNotification.created_at >= cutoff,
            )
            .order_by(UserNotification.created_at)
            .limit(100)
        )
        for notification, profile in result.all():
            if not (profile.notification_settings or {}).get("browser_notifications", False):
                continue
            if within_quiet_hours(
                local_now().time(),
                profile.notification_quiet_start,
                profile.notification_quiet_end,
            ):
                continue
            subscriptions = (
                await db.execute(
                    select(PushSubscription).where(
                        PushSubscription.user_id == notification.user_id
                    )
                )
            ).scalars().all()
            delivered = False
            for subscription in subscriptions:
                try:
                    await asyncio.to_thread(_send, subscription, notification)
                    subscription.failure_count = 0
                    subscription.last_error = None
                    delivered = True
                    sent += 1
                except WebPushException as exc:
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)
                    subscription.failure_count = (subscription.failure_count or 0) + 1
                    subscription.last_error = str(exc)[:300]
                    failed += 1
                    if status_code in {404, 410} or subscription.failure_count >= 3:
                        await db.delete(subscription)
                        removed += 1
                    logger.warning(
                        "Web Push delivery failed subscription=%s status=%s",
                        subscription.id,
                        status_code,
                    )
                except Exception as exc:
                    subscription.failure_count = (subscription.failure_count or 0) + 1
                    subscription.last_error = str(exc)[:300]
                    failed += 1
                    logger.warning("Web Push delivery failed subscription=%s", subscription.id)
            if delivered:
                notification.push_sent_at = datetime.now(timezone.utc)
        await db.commit()
    return {"enabled": True, "sent": sent, "failed": failed, "removed": removed}
