from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.notification import UserNotification
from app.models.user import User


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


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

