from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.deps import get_current_user
from app.models.notification import PushSubscription, UserNotification
from app.models.user import User
from app.services.web_push_service import web_push_public_config


router = APIRouter(prefix="/api/notifications", tags=["notifications"])
settings = get_settings()


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=255)
    auth: str = Field(min_length=8, max_length=255)


class PushSubscriptionBody(BaseModel):
    endpoint: str = Field(min_length=20, max_length=4096)
    keys: PushKeys


class PushUnsubscribeBody(BaseModel):
    endpoint: str = Field(min_length=20, max_length=4096)


def _validate_push_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    hostname = (parsed.hostname or "").lower()
    allowed = [item.lower().lstrip(".") for item in settings.WEB_PUSH_ALLOWED_HOST_SUFFIXES]
    if parsed.scheme != "https" or not hostname or not any(
        hostname == suffix or hostname.endswith(f".{suffix}") for suffix in allowed
    ):
        raise HTTPException(422, "Unsupported Web Push endpoint")


def _payload(item: UserNotification) -> dict:
    return {
        "id": str(item.id),
        "kind": item.kind,
        "title": item.title,
        "message": item.message,
        "payload": item.payload or {},
        "read_at": item.read_at.isoformat() if item.read_at else None,
        "created_at": item.created_at.isoformat(),
    }


@router.get("")
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    query = select(UserNotification).where(UserNotification.user_id == user.id)
    if unread_only:
        query = query.where(UserNotification.read_at.is_(None))
    result = await db.execute(query.order_by(UserNotification.created_at.desc()).limit(limit))
    count_result = await db.execute(
        select(func.count(UserNotification.id)).where(
            UserNotification.user_id == user.id,
            UserNotification.read_at.is_(None),
        )
    )
    return {
        "items": [_payload(item) for item in result.scalars().all()],
        "unread_count": int(count_result.scalar_one()),
    }


@router.post("/read-all")
async def read_all_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(UserNotification).where(
            UserNotification.user_id == user.id,
            UserNotification.read_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    items = result.scalars().all()
    for item in items:
        item.read_at = now
    return {"updated": len(items)}


@router.get("/push/config")
async def get_push_config(user: User = Depends(get_current_user)):
    del user
    return web_push_public_config()


@router.post("/push/subscriptions")
async def subscribe_push(
    body: PushSubscriptionBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not web_push_public_config()["enabled"]:
        raise HTTPException(503, "Web Push is not configured on the server")
    _validate_push_endpoint(body.endpoint)
    subscription = await db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    if subscription is None:
        subscription = PushSubscription(endpoint=body.endpoint, user_id=user.id)
        db.add(subscription)
    elif subscription.user_id != user.id:
        raise HTTPException(409, "Push subscription belongs to another account")
    subscription.user_id = user.id
    subscription.p256dh = body.keys.p256dh
    subscription.auth = body.keys.auth
    subscription.user_agent = (request.headers.get("user-agent") or "")[:300] or None
    subscription.failure_count = 0
    subscription.last_error = None
    await db.flush()
    return {"subscribed": True, "id": str(subscription.id)}


@router.delete("/push/subscriptions")
async def unsubscribe_push(
    body: PushUnsubscribeBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    subscription = await db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == user.id,
        )
    )
    if subscription is None:
        return {"removed": False}
    await db.delete(subscription)
    return {"removed": True}


@router.post("/{notification_id}/read")
async def read_notification(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(UserNotification).where(
            UserNotification.id == notification_id,
            UserNotification.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Notification not found")
    if item.read_at is None:
        item.read_at = datetime.now(timezone.utc)
    return _payload(item)
