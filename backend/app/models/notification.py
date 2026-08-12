import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class UserNotification(Base):
    __tablename__ = "user_notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_user_notifications_dedupe"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    title = Column(String(120), nullable=False)
    message = Column(String(500), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    dedupe_key = Column(String(160), nullable=False)
    read_at = Column(DateTime(timezone=True))
    push_sent_at = Column(DateTime(timezone=True), index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    user_agent = Column(String(300))
    failure_count = Column(Integer, nullable=False, default=0)
    last_error = Column(String(300))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PushDelivery(Base):
    __tablename__ = "push_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id",
            "subscription_id",
            name="uq_push_deliveries_notification_subscription",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("push_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), index=True)
    sent_at = Column(DateTime(timezone=True))
    last_error = Column(String(300))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
