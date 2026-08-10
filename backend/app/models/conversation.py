import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Text, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import enum


class RoleEnum(str, enum.Enum):
    system = "system"
    user = "user"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(SAEnum(RoleEnum), nullable=False)
    content = Column(Text, nullable=False)
    extra_metadata = Column("metadata", JSON)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
