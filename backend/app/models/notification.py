import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String, UniqueConstraint
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

